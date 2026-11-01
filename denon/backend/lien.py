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


@dataclass(frozen=True)
class Config:
    hote: str
    port: int
    cadence_s: float


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
        self.etat = {"connected": False, "power": None, "volume": None, "mute": None, "source": None, "updatedAt": None}
        self._file: asyncio.Queue = asyncio.Queue()
        self._ecrivain: asyncio.StreamWriter | None = None
        self.config = config()

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
        fut = asyncio.get_running_loop().create_future()
        self._file.put_nowait((commande, fut))
        await fut

    async def tourner(self) -> None:
        """La tâche de fond : connexion, lecture, envoi, reconnexion."""
        envoi = asyncio.create_task(self._vider())
        essais = 0
        try:
            while True:
                self.config = cfg = self._config()
                if not cfg.hote:
                    await asyncio.sleep(self.attente_max)
                    continue
                try:
                    lecteur, ecrivain = await asyncio.wait_for(asyncio.open_connection(cfg.hote, cfg.port), 5)
                except (OSError, asyncio.TimeoutError) as e:
                    self.journal.debug("ampli %s:%s injoignable : %s", cfg.hote, cfg.port, e)
                else:
                    essais = 0
                    await self._session(lecteur, ecrivain)
                await asyncio.sleep(min(self.attente_min * 2**essais, self.attente_max))
                essais += 1
        finally:
            envoi.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await envoi
            self._fermer()
            while not self._file.empty():
                _, fut = self._file.get_nowait()
                if not fut.done():
                    fut.set_exception(Injoignable("Proxy arrêté"))

    async def _session(self, lecteur: asyncio.StreamReader, ecrivain: asyncio.StreamWriter) -> None:
        self._ecrivain = ecrivain
        self.etat["connected"] = True
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

    async def _vider(self) -> None:
        while True:
            commande, fut = await self._file.get()
            if not fut.done():
                if self._ecrivain is None:
                    fut.set_exception(Injoignable("Ampli injoignable"))
                else:
                    try:
                        self._ecrivain.write(f"{commande}\r".encode("ascii"))
                        await self._ecrivain.drain()
                        fut.set_result(None)
                    except OSError as e:
                        fut.set_exception(Injoignable(str(e)))
            await asyncio.sleep(self.config.cadence_s)
