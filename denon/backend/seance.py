"""La séance du réveil : ce qui se passe quand une alarme part.

Conception : `docs/reveil.md`, « La séance ». Une seule séance à la fois ;
une alarme qui part pendant une séance la remplace.

1. **Préparer**, avant de toucher à l'ampli : l'adresse réseau d'unisson,
   le lien telnet, les formats du lecteur (`GetProtocolInfo`, une fois par
   séance), les pistes, et le flux de la première. Si l'une manque, l'ampli
   n'est pas réveillé pour rien : le résultat le dit.
2. **Allumer** : `PWON`, le volume de départ, la source réseau du pilote.
   On prend la main quelle que soit la source.
3. **Attendre** le délai de sortie de veille (`GetTransportInfo` répond
   déjà en veille et ne prouve rien), renvoyer volume et source (une
   commande reçue pendant le réveil a pu se perdre), puis `Play` jusqu'à
   `PLAYING`, 3 essais au plus.
4. **Jouer** : `SetAVTransportURI` → `Play` → `marquer_jouee`, puis la
   suivante en attente (`SetNextAVTransportURI`). **Repli** si l'ampli
   refuse `SetNext` (faute UPnP) ou s'arrête en fin de piste sans enchaîner :
   `SetAVTransportURI` + `Play` de la suivante.
5. **Suivre** toutes les `suivi_s` : quand `TrackURI` passe à la suivante,
   `marquer_jouee` et on met en attente celle d'après. Une piste dont le
   flux est impossible est sautée et journalisée.
6. **Monter le volume** par pas de 0,5 dB, sur `montee_s`. La montée
   s'arrête si l'ampli pousse un volume que nous n'avons pas envoyé.
7. **Finir** : `duree` → `Stop` puis `PWSTANDBY` ; `pistes` → `PWSTANDBY`
   après la dernière ; `sans_limite` → jamais seul. Quelqu'un qui reprend la
   main (autre source, `Stop` ou `Pause` venus d'ailleurs, autre média,
   mise en veille) arrête la séance, sans mise en veille.

Un `STOPPED` est une fin de piste si la piste a joué au moins sa durée
moins `1,5 × suivi_s + marge_fin_s` (le début de la piste est recalé sur
chaque `RelTime` lu ; une durée inconnue compte comme une fin) ; sinon
c'est un `Stop` venu d'ailleurs.

Le résultat final va dans `dernier_resultat` (40 caractères au plus) :
`joue`, `reprise_en_main`, `arretee`, `remplacee`, `ampli_injoignable`,
`adresse_reseau_non_reglee`, `aucune_piste`, `aucun_format_commun` (ou un
autre code de `FluxImpossible`), `lecture_impossible`, `pistes_epuisees`,
`plugin_desactive`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from unisson.plugin import AdresseReseauNonReglee, FluxImpossible

from . import alarmes
from .dlna import ErreurDlna, ErreurUpnp, LecteurDlna, meme_piste
from .lien import Injoignable, Lien
from .pilotes import lire_volume

LOT = 50  # pistes tirées à la fois, rechargées quand elles s'épuisent
_SAUTEES_GARDEES = 20


@dataclass(frozen=True)
class Cadence:
    """Les durées de la séance ; les tests les raccourcissent."""

    suivi_s: float = 2.0  # entre deux lectures de l'état du lecteur
    minute_s: float = 60.0  # l'unité de `fin_valeur` en mode `duree`
    attente_lien_s: float = 5.0  # le lien telnet se reconnecte peut-être
    essais_play: int = 3
    attente_play_s: float = 4.0  # après un `Play`, le temps d'atteindre PLAYING
    pas_db: float = 0.5
    echecs_suivi_max: int = 3  # lectures d'état ratées d'affilée : ampli perdu
    arret_s: float = 5.0  # borne du nettoyage quand on arrête une séance
    marge_fin_s: float = 1.0  # un STOPPED à moins de 1,5 × suivi_s + ceci de la fin : fin de piste


class Echec(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code[: alarmes.RESULTAT_MAX]
        self.message = message or code


@dataclass(frozen=True)
class Piste:
    id: int
    flux: object  # FluxLecteur


def _vue_piste(p: Piste | None) -> dict | None:
    if p is None:
        return None
    f = p.flux
    return {"id": p.id, "titre": f.titre, "artiste": f.artiste, "album": f.album, "pochette": f.pochette,
            "duree": f.duree, "converti": f.converti}


def maintenant_utc() -> datetime:
    return datetime.now(timezone.utc)


class Seance:
    def __init__(self, alarme: dict, ctx, lien: Lien, lecteur: LecteurDlna, *, delai_reveil_s: float,
                 cadence: Cadence, journal: logging.Logger, maintenant: Callable[[], datetime] = maintenant_utc):
        self.alarme = alarme
        self.ctx = ctx
        self.lien = lien
        self.pilote = lien.pilote
        self.lecteur = lecteur
        self.delai_reveil_s = max(0.0, delai_reveil_s)
        self.cadence = cadence
        self.journal = journal
        self.maintenant = maintenant

        self.etat = "preparation"  # puis reveil, lecture, finie
        self.debut = maintenant()
        self._t0 = time.monotonic()
        self.fin_prevue: datetime | None = None
        if alarme["fin_mode"] == "duree":
            self.fin_prevue = self.debut + timedelta(seconds=alarme["fin_valeur"] * cadence.minute_s)
        self.resultat: str | None = None
        self.motif_arret: str | None = None  # posé avant d'annuler la tâche

        self.accepte: list[str] = []
        self.file: deque[int] = deque()
        self.rechargeable = alarme["fin_mode"] != "pistes"
        self._succes_depuis_charge = True
        self._dernier_refus: str | None = None
        self.courante: Piste | None = None
        self.suivante: Piste | None = None
        self._suivante_posee = False
        self.repli = False  # SetNext refusé, ou l'ampli n'enchaîne pas
        self.jouees = 0
        self.sautees: list[dict] = []

        self.montee = "sans"  # en_cours, finie, interrompue
        self._envoyes: list[float] = []  # les volumes envoyés, tels que l'ampli les rendra
        self._echo_vu = False
        self._source_vue = False
        self._allume_vu = False
        self._tache_montee: asyncio.Task | None = None
        self._debut_piste = 0.0  # instant (monotone) où la piste courante a commencé
        self._duree_piste: float | None = None  # TrackDuration lu, sinon celle du flux

    @property
    def ident(self) -> int:
        return self.alarme["id"]

    def _log(self, niveau: int, message: str, *args) -> None:
        self.journal.log(niveau, "séance de l'alarme %s : " + message, self.ident, *args)

    # ── 1. préparer ─────────────────────────────────────────────────────

    async def preparer(self) -> None:
        """Tout ce qui se vérifie sans réveiller l'ampli ; lève `Echec`."""
        try:
            self.ctx.adresse_reseau()
        except AdresseReseauNonReglee as e:
            raise Echec(e.code, e.libelle) from None
        if not await self._attendre_lien():
            raise Echec("ampli_injoignable", "le lien telnet n'est pas connecté")
        try:
            self.accepte = await self.lecteur.protocoles()
        except ErreurDlna as e:
            raise Echec("ampli_injoignable", f"UPnP : {e}") from None
        self._log(logging.INFO, "%d format(s) annoncé(s) par le lecteur", len(self.accepte))
        try:
            ids = await self._tirer()
        except FluxImpossible as e:
            raise Echec(e.code, e.libelle) from None
        if not ids:
            raise Echec("aucune_piste", "aucune piste à jouer dans ce contexte")
        self.file.extend(ids)
        self.courante = await self._prochaine()
        if self.courante is None:
            raise Echec(self._dernier_refus or "aucune_piste", "aucune piste jouable par ce lecteur")

    async def _attendre_lien(self) -> bool:
        fin = time.monotonic() + self.cadence.attente_lien_s
        while not self.lien.connecte:
            if time.monotonic() >= fin:
                return False
            await asyncio.sleep(0.05)
        return True

    async def _tirer(self) -> list[int]:
        a = self.alarme
        n = a["fin_valeur"] if a["fin_mode"] == "pistes" else LOT
        if a["contexte"] == "playlist":
            ids = await self.ctx.pistes_playlist(a["contexte_id"])
            if a["melange"]:
                random.shuffle(ids)
            return ids[:n]
        return await self.ctx.tirer_pistes(
            a["contexte"], a["contexte_id"], n=n,
            genre_id=a["genre_id"], format=a["format"], favoris=bool(a["favoris"]),
        )

    async def _prochaine(self) -> Piste | None:
        """La prochaine piste jouable ; les flux impossibles sont sautés. Un
        lot rechargé dont aucune piste n'a pu partir arrête les recharges."""
        while True:
            if not self.file:
                if not self.rechargeable or not self._succes_depuis_charge:
                    return None
                try:
                    ids = await self._tirer()
                except FluxImpossible as e:
                    self._log(logging.WARNING, "recharge impossible : %s", e.libelle)
                    return None
                if not ids:
                    return None
                self._log(logging.INFO, "%d piste(s) rechargée(s)", len(ids))
                self.file.extend(ids)
                self._succes_depuis_charge = False
            pid = self.file.popleft()
            try:
                flux = await self.ctx.flux_lecteur(pid, self.accepte, self.pilote.plafond)
            except AdresseReseauNonReglee as e:
                self._dernier_refus = e.code
                self._log(logging.WARNING, "%s", e.libelle)
                self.file.clear()
                self.rechargeable = False
                return None
            except FluxImpossible as e:
                self._sauter(pid, e.code, e.libelle)
                continue
            except Exception as e:  # la base qui hoquette ne doit pas couper le réveil
                self._sauter(pid, "erreur", repr(e))
                continue
            self._succes_depuis_charge = True
            if flux.converti:
                self._log(logging.INFO, "piste %s convertie (%s)", pid, flux.motif)
            return Piste(pid, flux)

    def _sauter(self, pid: int, code: str, libelle: str) -> None:
        self._dernier_refus = code
        self._log(logging.WARNING, "piste %s sautée (%s) : %s", pid, code, libelle)
        self.sautees.append({"piste": pid, "code": code, "libelle": libelle})
        del self.sautees[:-_SAUTEES_GARDEES]

    # ── 2 à 7. dérouler ─────────────────────────────────────────────────

    async def derouler(self) -> str:
        """La séance entière ; rend le code du résultat, sans jamais lever
        (une annulation porte son motif : `motif_arret`)."""
        try:
            code = await self._derouler()
        except Echec as e:
            self._log(logging.WARNING, "%s (%s)", e.message, e.code)
            code = e.code
        except asyncio.CancelledError:
            if (tache := asyncio.current_task()) is not None:
                tache.uncancel()
            code = self.motif_arret or "interrompue"
            self._log(logging.INFO, "arrêtée (%s)", code)
            if self.motif_arret == "arretee" and self.etat == "lecture":
                with contextlib.suppress(ErreurDlna, asyncio.TimeoutError):
                    async with asyncio.timeout(self.cadence.arret_s):
                        await self.lecteur.arreter()
        except Exception as e:
            self._log(logging.ERROR, "erreur inattendue : %r", e)
            self.journal.exception("séance de l'alarme %s", self.ident)
            code = f"erreur:{type(e).__name__}"
        finally:
            if self._tache_montee is not None:
                self._tache_montee.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._tache_montee
            self.etat = "finie"
        self.resultat = code[: alarmes.RESULTAT_MAX]
        self._log(logging.INFO, "finie : %s (%d piste(s) jouée(s))", self.resultat, self.jouees)
        return self.resultat

    async def _derouler(self) -> str:
        a, p = self.alarme, self.pilote
        self.etat = "reveil"
        depart = a["volume_cible_db"] if a["montee_s"] == 0 else a["volume_depart_db"]
        try:
            await self.lien.envoyer(p.alimentation(True))
            await self._volume(depart)
            if p.source_reseau:
                await self.lien.envoyer(p.source_reseau)
        except Injoignable as e:
            raise Echec("ampli_injoignable", f"telnet : {e}") from None
        self._log(logging.INFO, "ampli allumé, %s dB ; attente de %g s", depart, self.delai_reveil_s)
        await asyncio.sleep(self.delai_reveil_s)
        # Une commande reçue pendant la sortie de veille a pu se perdre.
        with contextlib.suppress(Injoignable):
            await self._volume(depart)
            if p.source_reseau:
                await self.lien.envoyer(p.source_reseau)

        await self._lancer_lecture()
        self.etat = "lecture"
        await self._marquer(self.courante)
        await self._mettre_en_attente()
        if a["montee_s"] > 0 and a["volume_depart_db"] != a["volume_cible_db"]:
            self.montee = "en_cours"
            self._tache_montee = asyncio.create_task(self._monter())
        return await self._suivre()

    async def _volume(self, db: float) -> None:
        commande = self.pilote.volume(db)
        self._envoyes.append(lire_volume(commande[2:]))
        await self.lien.envoyer(commande)

    async def _lancer_lecture(self) -> None:
        derniere = ""
        n = self.cadence.essais_play
        for essai in range(1, n + 1):
            try:
                await self.lecteur.definir_uri(self.courante.flux)
                # Le début de la piste, au plus tôt : une réponse lente ne
                # doit pas faire prendre une fin de piste pour un Stop.
                self._debut_piste = time.monotonic()
                await self.lecteur.jouer()
                if await self._attendre_lecture():
                    self._log(logging.INFO, "lecture lancée (essai %d/%d) : piste %s", essai, n, self.courante.id)
                    return
                derniere = "le lecteur n'est pas passé en lecture"
            except ErreurDlna as e:
                derniere = str(e)
            self._log(logging.INFO, "essai %d/%d de lecture raté : %s", essai, n, derniere)
            if essai < n:
                await asyncio.sleep(self.cadence.suivi_s)
        raise Echec("lecture_impossible", derniere)

    async def _attendre_lecture(self) -> bool:
        fin = time.monotonic() + self.cadence.attente_play_s
        pause = max(0.02, min(0.5, self.cadence.attente_play_s / 8))
        while True:
            with contextlib.suppress(ErreurDlna):
                if (await self.lecteur.etat()).etat == "PLAYING":
                    return True
            if time.monotonic() >= fin:
                return False
            await asyncio.sleep(pause)

    async def _marquer(self, piste: Piste) -> None:
        try:
            await self.ctx.marquer_jouee(piste.id)
        except Exception as e:  # piste supprimée entre-temps, plugin désactivé
            self._log(logging.WARNING, "marquer_jouee(%s) : %s", piste.id, e)
        self.jouees += 1

    async def _mettre_en_attente(self) -> None:
        if self.suivante is None:
            self.suivante = await self._prochaine()
            self._suivante_posee = False
        if self.suivante is None or self.repli or self._suivante_posee:
            return
        try:
            await self.lecteur.definir_suivante(self.suivante.flux)
            self._suivante_posee = True
        except ErreurUpnp as e:
            self.repli = True
            self._log(logging.WARNING, "SetNextAVTransportURI refusé (%s) : repli sur SetAVTransportURI", e)
        except ErreurDlna as e:
            self._log(logging.INFO, "SetNextAVTransportURI : %s ; nouvel essai au prochain suivi", e)

    async def _suivre(self) -> str:
        c = self.cadence
        marge = 1.5 * c.suivi_s + c.marge_fin_s
        echecs = 0
        while True:
            attente = c.suivi_s
            if self.fin_prevue is not None:
                reste = (self.fin_prevue - self.maintenant()).total_seconds()
                if reste <= 0:
                    self._log(logging.INFO, "durée atteinte : Stop puis veille")
                    with contextlib.suppress(ErreurDlna):
                        await self.lecteur.arreter()
                    await self._veille()
                    return "joue"
                attente = min(attente, reste)
            await asyncio.sleep(attente)
            if motif := self._reprise_telnet():
                return self._reprise(motif)
            try:
                etat = (await self.lecteur.etat()).etat
                avant = time.monotonic()  # RelTime est lu après : début au plus tôt
                pos = await self.lecteur.position()
            except ErreurDlna as e:
                echecs += 1
                self._log(logging.INFO, "suivi raté (%d/%d) : %s", echecs, c.echecs_suivi_max, e)
                if echecs >= c.echecs_suivi_max:
                    return "ampli_injoignable"
                continue
            echecs = 0

            uri = pos.uri
            if self.suivante and uri and meme_piste(uri, self.suivante.flux.url) and not meme_piste(uri, self.courante.flux.url):
                self._log(logging.INFO, "enchaîné sur la piste %s", self.suivante.id)
                self._debut_piste = avant - (pos.temps_s or 0.0)
                await self._avancer()
            elif uri and not meme_piste(uri, self.courante.flux.url):
                return self._reprise(f"le lecteur joue autre chose ({uri})")

            if etat in ("PLAYING", "TRANSITIONING"):
                if etat == "PLAYING" and (t := pos.temps_s) is not None:
                    self._debut_piste = avant - t
                if pos.duree_s:
                    self._duree_piste = pos.duree_s
                if not self._suivante_posee:
                    await self._mettre_en_attente()
                continue
            if etat == "PAUSED_PLAYBACK":
                return self._reprise("mise en pause depuis ailleurs")
            if etat not in ("STOPPED", "NO_MEDIA_PRESENT"):
                continue
            # Fin de piste ou Stop venu d'ailleurs : le temps écoulé depuis le
            # début de la piste (recalé sur chaque `RelTime` lu) le dit.
            d = self._duree_piste or self.courante.flux.duree
            if d is not None and time.monotonic() - self._debut_piste < d - marge:
                return self._reprise("arrêtée depuis ailleurs")
            if self.suivante is None:
                if self.alarme["fin_mode"] == "sans_limite":
                    return "pistes_epuisees"
                self._log(logging.INFO, "dernière piste jouée : veille")
                await self._veille()
                return "joue"
            await self._repli()

    async def _avancer(self) -> None:
        self.courante, self.suivante, self._suivante_posee = self.suivante, None, False
        self._duree_piste = None
        await self._marquer(self.courante)
        await self._mettre_en_attente()

    async def _repli(self) -> None:
        if not self.repli:
            self.repli = True
            self._log(logging.WARNING, "l'ampli n'a pas enchaîné : repli sur SetAVTransportURI")
        try:
            await self.lecteur.definir_uri(self.suivante.flux)
            debut = time.monotonic()
            await self.lecteur.jouer()
        except ErreurDlna as e:
            raise Echec("lecture_impossible", f"repli : {e}") from None
        self._log(logging.INFO, "repli : piste %s lancée", self.suivante.id)
        self._debut_piste = debut
        await self._avancer()

    def _reprise_telnet(self) -> str | None:
        etat = self.lien.etat
        if self.pilote.source_reseau:
            if self.pilote.est_source_reseau(etat["source"]):
                self._source_vue = True
            elif self._source_vue and etat["source"]:
                return f"autre source ({etat['source']})"
        if etat["power"] is True:
            self._allume_vu = True
        elif self._allume_vu and etat["power"] is False:
            return "ampli mis en veille"
        return None

    def _reprise(self, motif: str) -> str:
        self._log(logging.INFO, "quelqu'un reprend la main : %s", motif)
        return "reprise_en_main"

    async def _veille(self) -> None:
        try:
            await self.lien.envoyer(self.pilote.alimentation(False))
        except Injoignable as e:
            self._log(logging.WARNING, "mise en veille impossible : %s", e)

    async def _monter(self) -> None:
        """Le volume suit une droite du départ à la cible, arrondie au pas.
        Si l'envoi prend du retard (la cadence du lien), on saute au pas
        du moment plutôt que de rattraper un à un."""
        a, c = self.alarme, self.cadence
        depart, cible, duree = a["volume_depart_db"], a["volume_cible_db"], a["montee_s"]
        ecart = abs(cible - depart)
        n = max(1, math.ceil(ecart / c.pas_db - 1e-9))
        sens = 1 if cible > depart else -1
        t0 = time.monotonic()
        fait = 0
        while fait < n:
            k = min(n, max(fait + 1, math.floor((time.monotonic() - t0) / duree * n + 1e-9)))
            await asyncio.sleep(max(0.0, t0 + duree * k / n - time.monotonic()))
            if self._volume_touche():
                self.montee = "interrompue"
                self._log(logging.INFO, "volume touché (%s dB) : la montée s'arrête", self.lien.etat["volume"])
                return
            try:
                await self._volume(depart + sens * min(c.pas_db * k, ecart))
            except Injoignable as e:
                self.montee = "interrompue"
                self._log(logging.WARNING, "montée interrompue : %s", e)
                return
            fait = k
        self.montee = "finie"

    def _volume_touche(self) -> bool:
        """L'ampli a poussé un volume que nous n'avons pas envoyé. On ne juge
        qu'après avoir vu l'écho d'un de nos pas : avant, l'état peut garder
        le volume d'avant la séance."""
        v = self.lien.etat["volume"]
        if v is None:
            return False
        if any(abs(v - e) < 0.05 for e in self._envoyes):
            self._echo_vu = True
            return False
        return self._echo_vu

    # ── la vue ──────────────────────────────────────────────────────────

    def vue(self, fuseau) -> dict:
        a = self.alarme
        restantes = None
        if a["fin_mode"] == "pistes":
            restantes = len(self.file) + (self.suivante is not None)
        return {
            "alarme": {"id": a["id"], "nom": a["nom"]},
            "etat": self.etat,
            "debut": alarmes.local(self.debut, fuseau),
            "piste": _vue_piste(self.courante),
            "suivante": _vue_piste(self.suivante),
            "volume": self.lien.etat["volume"],
            "volume_depart": a["volume_depart_db"],
            "volume_cible": a["volume_cible_db"],
            "montee": self.montee,
            "fin_mode": a["fin_mode"],
            "fin_prevue": alarmes.local(self.fin_prevue, fuseau),
            "pistes_restantes": restantes,
            "pistes_jouees": self.jouees,
            "sautees": list(self.sautees),
            "enchainement": "repli" if self.repli else "suivante",
            "resultat": self.resultat,
        }


class Seances:
    """La séance en cours (une seule), lancée par l'ordonnanceur
    (`declencher`) ou par `essayer`. `tourner()` est la tâche de fond du
    plugin : à la désactivation, elle arrête la séance et ferme le client
    UPnP."""

    def __init__(self, ctx, lien: Lien, lecteur: LecteurDlna, session: Callable, *,
                 fuseau: Callable, delai_reveil_s: Callable[[], float] | None = None,
                 cadence: Cadence = Cadence(), ordonnanceur=None, journal: logging.Logger | None = None,
                 maintenant: Callable[[], datetime] = maintenant_utc):
        self.ctx = ctx
        self.lien = lien
        self.lecteur = lecteur
        self.session = session
        self.fuseau = fuseau
        self.delai_reveil_s = delai_reveil_s or (lambda: lien.pilote.delai_reveil_s)
        self.cadence = cadence
        self.ordonnanceur = ordonnanceur
        self.journal = journal or logging.getLogger("unisson.plugin.denon")
        self.maintenant = maintenant
        self.courante: Seance | None = None
        self.derniere: dict | None = None
        self._tache: asyncio.Task | None = None
        self._verrou = asyncio.Lock()
        self._ferme = False

    @property
    def en_cours(self) -> bool:
        return self._tache is not None and not self._tache.done()

    async def declencher(self, alarme: dict) -> str | None:
        """L'accroche de l'ordonnanceur : rend le code d'un échec de
        préparation, ou None quand la séance tourne (elle écrira son résultat)."""
        self.journal.info("alarme %s « %s » déclenchée (%s)", alarme["id"], alarme["nom"], alarme["heure"])
        code = await self.lancer(alarme)
        return None if code == "en_cours" else code

    async def lancer(self, alarme: dict, *, ecrire: bool = False) -> str:
        """Prépare puis lance la séance de cette alarme, à la place de celle
        en cours. Rend `"en_cours"`, ou le code de l'échec de préparation (la
        séance en cours, s'il y en a une, continue alors). `ecrire` : noter
        le résultat dans l'alarme (l'ordonnanceur le fait lui-même)."""
        if self._ferme:
            return "plugin_desactive"
        seance = Seance(alarme, self.ctx, self.lien, self.lecteur, delai_reveil_s=self.delai(),
                        cadence=self.cadence, journal=self.journal, maintenant=self.maintenant)
        try:
            await seance.preparer()
        except Echec as e:
            seance._log(logging.WARNING, "pas de séance : %s (%s)", e.message, e.code)
            seance.etat, seance.resultat = "finie", e.code
            self.derniere = seance.vue(self.fuseau())
            self.derniere["message"] = e.message
            if ecrire:
                await self._noter(alarme["id"], e.code)
            return e.code
        async with self._verrou:
            if self._ferme:
                return "plugin_desactive"
            await self._arreter("remplacee")
            if ecrire:
                await self._noter(alarme["id"], "en_cours")
            self.courante = seance
            self._tache = asyncio.create_task(self._vivre(seance), name=f"denon:seance:{alarme['id']}")
        return "en_cours"

    def delai(self) -> float:
        try:
            return float(self.delai_reveil_s())
        except (TypeError, ValueError):
            return self.lien.pilote.delai_reveil_s

    async def _vivre(self, seance: Seance) -> None:
        code = await seance.derouler()
        self.derniere = seance.vue(self.fuseau())
        if self.courante is seance:
            self.courante = None
        await self._noter(seance.ident, code)
        if self.ordonnanceur is not None:
            self.ordonnanceur.resultat_tardif(seance.ident, code)

    async def _noter(self, ident: int, code: str) -> None:
        try:
            async with asyncio.timeout(self.cadence.arret_s):
                async with self.session() as s:
                    await alarmes.noter_resultat(s, ident, code)
                    await s.commit()
        except Exception as e:  # la base ne doit pas faire tomber la séance
            self.journal.warning("alarme %s : résultat « %s » non noté (%r)", ident, code, e)

    async def arreter(self, motif: str = "arretee") -> bool:
        """Arrête la séance en cours, sans mise en veille ; faux s'il n'y en
        avait pas."""
        async with self._verrou:
            return await self._arreter(motif)

    async def _arreter(self, motif: str) -> bool:
        tache, seance = self._tache, self.courante
        if tache is None or tache.done():
            return False
        if seance is not None:
            seance.motif_arret = motif
        tache.cancel()
        await asyncio.wait({tache}, timeout=2 * self.cadence.arret_s)
        return True

    def vue(self) -> dict:
        fz = self.fuseau()
        return {
            "seance": self.courante.vue(fz) if self.courante is not None and self.en_cours else None,
            "derniere": self.derniere,
        }

    async def tourner(self) -> None:
        """La tâche de fond : rien à faire qu'attendre la désactivation, puis
        ne rien laisser derrière (séance, client HTTP)."""
        try:
            await asyncio.Event().wait()
        finally:
            self._ferme = True
            tache = self._tache
            if tache is not None and not tache.done():
                if self.courante is not None:
                    self.courante.motif_arret = "plugin_desactive"
                tache.cancel()
                await asyncio.wait({tache}, timeout=2 * self.cadence.arret_s)
            await self.lecteur.fermer()
