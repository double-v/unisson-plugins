"""Le lien telnet unique vers l'ampli, partagé par tous les clients.

Un AVR n'accepte qu'une connexion telnet, et perd les commandes trop
rapprochées : le lien garde une seule socket, met les commandes en file et
les envoie à une cadence fixe, se reconnecte avec un délai qui double
(1 s → 30 s), et tient l'état poussé par l'ampli. Réécriture en Python de
`denon-api` (`server/denon-link.js`), au comportement près :

- une commande invalide est refusée avant la file ;
- une commande sortie de la file pendant que l'ampli est injoignable est
  refusée (`Injoignable`), jamais gardée pour plus tard ;
- la cadence s'applique après chaque commande, refusée ou non.

La configuration est relue à chaque connexion : changer d'hôte ou de port
prend effet à la reconnexion suivante.

Deux façons de suivre l'ampli : `ecouter()`, chaque trame qui change l'état
(la séance du réveil) ; `abonner()`, chaque nouvel état complet, connexion et
coupure du lien comprises (le flux `/api/events`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


class Injoignable(Exception):
    """L'ampli n'est pas connecté au moment d'envoyer."""


# Erreurs d'une configuration fausse (port hors bornes, hôte illisible) :
# journalisées et réessayées comme une panne réseau, jamais fatales.
ERREURS_DE_CONNEXION = (OSError, asyncio.TimeoutError, OverflowError, UnicodeError, ValueError)


@dataclass(frozen=True)
class Config:
    hote: str
    port: int
    cadence_s: float


class Abonnement:
    """Les états successifs du lien pour un client : un état complet remplace
    le précédent non lu. Un client lent trouve le dernier état, jamais une
    file qui grossit, et un client qui suit l'ampli n'a besoin que de lui."""

    def __init__(self, retirer: Callable[["Abonnement"], None]):
        self._retirer = retirer
        self._dernier: dict | None = None
        self._signal = asyncio.Event()
        self.ferme = False

    def _pousser(self, etat: dict) -> None:
        self._dernier = etat
        self._signal.set()

    def _clore(self) -> None:
        self.ferme = True
        self._signal.set()

    async def suivant(self, delai: float) -> dict | None:
        """Le dernier état non lu ; `None` après `delai` s sans changement, ou
        tout de suite une fois l'abonnement fermé (voir `ferme`)."""
        if self._dernier is None and not self.ferme:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._signal.wait(), delai)
        self._signal.clear()
        etat, self._dernier = self._dernier, None
        return etat

    def retirer(self) -> None:
        self._retirer(self)


class Lien:
    def __init__(
        self,
        config: Callable[[], Config],
        pilote,
        *,
        attente_min: float = 1.0,
        attente_max: float = 30.0,
        journal: logging.Logger | None = None,
    ):
        self._config = config
        self.pilote = pilote
        self.attente_min = attente_min
        self.attente_max = attente_max
        self.journal = journal or logging.getLogger("unisson.plugin.denon")
        self.etat = {"connected": False, "power": None, "volume": None, "mute": None, "source": None, "zone": None,
                     "updatedAt": None}
        self._file: asyncio.Queue = asyncio.Queue()
        self._ecrivain: asyncio.StreamWriter | None = None
        self._arrete = False
        self.config = config()
        self._ecouteurs: list[Callable[[str], None]] = []
        self._abonnes: list[Abonnement] = []
        self._diffuse = self._vu()

    def ecouter(self, ecouteur: Callable[[str], None]) -> Callable[[], None]:
        """Appelle `ecouteur(trame)` pour chaque trame qui change l'état, dans
        l'ordre d'arrivée ; rend de quoi se désabonner. Un instantané de
        `etat` peut manquer un geste entre deux lectures, pas un écouteur."""
        self._ecouteurs.append(ecouteur)

        def retirer() -> None:
            if ecouteur in self._ecouteurs:
                self._ecouteurs.remove(ecouteur)

        return retirer

    def abonner(self) -> Abonnement:
        """Un abonnement aux nouveaux états ; `retirer()` pour s'en aller.
        Lien arrêté : l'abonnement naît fermé."""

        def retirer(a: Abonnement) -> None:
            if a in self._abonnes:
                self._abonnes.remove(a)

        a = Abonnement(retirer)
        if self._arrete:
            a._clore()
        else:
            self._abonnes.append(a)
        return a

    def _vu(self) -> dict:
        return {k: v for k, v in self.etat.items() if k != "updatedAt"}

    def _diffuser(self) -> None:
        """Pousse l'état aux abonnés s'il a changé : l'ampli répète volontiers
        une trame (`PWON` à chaque requête `PW?`), sans rien changer."""
        if (vu := self._vu()) == self._diffuse:
            return
        self._diffuse = vu
        etat = dict(self.etat)
        for a in list(self._abonnes):
            a._pousser(etat)

    @property
    def connecte(self) -> bool:
        return self._ecrivain is not None

    @property
    def en_attente(self) -> int:
        return self._file.qsize()

    async def envoyer(self, commande: str) -> None:
        """Met une commande en file ; rend la main quand elle est partie."""
        if not self.pilote.valider(commande):
            raise ValueError("Commande Denon invalide")
        if self._arrete:
            raise Injoignable("Proxy arrêté")
        fut = asyncio.get_running_loop().create_future()
        self._file.put_nowait((commande, fut))
        await fut

    async def tourner(self) -> None:
        """La tâche de fond : connexion, lecture, envoi, reconnexion."""
        self._arrete = False
        envoi = asyncio.create_task(self._vider())
        essais = 0
        try:
            while True:
                if envoi.done():  # l'envoi ne doit jamais mourir en silence
                    raise RuntimeError("la file d'envoi s'est arrêtée") from envoi.exception()
                self.config = cfg = self._config()
                if not cfg.hote:
                    await asyncio.sleep(self.attente_max)
                    continue
                try:
                    lecteur, ecrivain = await asyncio.wait_for(asyncio.open_connection(cfg.hote, cfg.port), 5)
                except ERREURS_DE_CONNEXION as e:
                    self.journal.debug("ampli %s:%s injoignable : %s", cfg.hote, cfg.port, e)
                else:
                    essais = 0
                    await self._session(lecteur, ecrivain)
                await asyncio.sleep(min(self.attente_min * 2**essais, self.attente_max))
                essais = min(essais + 1, 16)  # 2**essais ne déborde jamais
        finally:
            self._arrete = True
            envoi.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await envoi
            self._fermer()
            while not self._file.empty():
                _, fut = self._file.get_nowait()
                if not fut.done():
                    fut.set_exception(Injoignable("Proxy arrêté"))
            # Les flux en cours se terminent : le plugin est désactivé.
            for a in self._abonnes:
                a._clore()
            self._abonnes.clear()

    async def _session(self, lecteur: asyncio.StreamReader, ecrivain: asyncio.StreamWriter) -> None:
        self._ecrivain = ecrivain
        self.etat["connected"] = True
        self._diffuser()
        self.journal.info("ampli connecté (%s:%s)", self.config.hote, self.config.port)
        for requete in self.pilote.requetes_initiales:
            fut = asyncio.get_running_loop().create_future()
            self._file.put_nowait((requete, fut))
            fut.add_done_callback(lambda f: f.exception())  # personne ne l'attend
        tampon = ""
        try:
            while morceau := await lecteur.read(4096):
                tampon += morceau.decode("ascii", "replace")
                *lignes, tampon = tampon.split("\r")
                for ligne in lignes:
                    if (ligne := ligne.strip()) and self.pilote.lire(self.etat, ligne):
                        self.etat["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                        for ecouteur in list(self._ecouteurs):
                            try:
                                ecouteur(ligne)
                            except Exception:  # un écouteur ne coupe pas le lien
                                self.journal.exception("écouteur du lien")
                        self._diffuser()
        except OSError as e:
            self.journal.debug("lien coupé : %s", e)
        finally:
            self._fermer()
            self.journal.info("ampli déconnecté")

    def _fermer(self) -> None:
        if self._ecrivain is not None:
            self._ecrivain.close()
        self._ecrivain = None
        self.etat["connected"] = False
        self._diffuser()

    async def _vider(self) -> None:
        while True:
            commande, fut = await self._file.get()
            if fut.done():  # client parti : pas de créneau consommé
                continue
            try:
                if self._ecrivain is None:
                    fut.set_exception(Injoignable("Ampli injoignable"))
                else:
                    try:
                        self._ecrivain.write(f"{commande}\r".encode("ascii"))
                        await self._ecrivain.drain()
                        fut.set_result(None)
                    except OSError as e:
                        fut.set_exception(Injoignable(str(e)))
            finally:
                if not fut.done():  # annulée pendant drain()
                    fut.set_exception(Injoignable("Proxy arrêté"))
            await asyncio.sleep(self.config.cadence_s)
