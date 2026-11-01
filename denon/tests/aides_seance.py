"""Les aides des tests de la séance : un DMR à états, des pistes en base.

`DmrAEtats` est un vrai serveur HTTP (le faux lecteur de `aides_dlna.py`)
qui tient un état de transport comme un lecteur : `Play` le fait jouer,
`RelTime` avance avec le temps réel, la piste suivante (`SetNext…`) prend
le relais en fin de piste. On peut lui faire refuser `Play` (sortie de
veille), refuser `SetNext`, ne pas enchaîner, ou subir un `Stop`, une
`Pause` ou un autre média venus d'ailleurs.
"""

import re
import socket
import time

from denon.backend.dlna import secondes
from denon.tests.aides_dlna import AVT, FauxLecteur, faute

CM = "urn:schemas-upnp-org:service:ConnectionManager:1"
# Ce que l'AVR-X4000 annonce, en résumé : FLAC, MP3, L16.
SINK = ",".join([
    "http-get:*:audio/x-flac:*",
    "http-get:*:audio/mpeg:*",
    "http-get:*:audio/L16;rate=44100;channels=2:*",
    "http-get:*:audio/L16;rate=48000;channels=2:*",
])


def _enveloppe(action: str, champs: dict, urn: str = AVT) -> bytes:
    corps = "".join(f"<{k}>{v}</{k}>" for k, v in champs.items())
    return (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action}Response xmlns:u="{urn}">{corps}</u:{action}Response></s:Body></s:Envelope>'
    ).encode()


def _temps(s: float | None) -> str:
    if s is None:
        return "NOT_IMPLEMENTED"
    h, reste = divmod(max(0.0, s), 3600)
    m, sec = divmod(reste, 60)
    return f"{int(h)}:{int(m):02}:{sec:06.3f}"


def _x(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class DmrAEtats(FauxLecteur):
    def __init__(self, sink: str = SINK):
        super().__init__()
        self.reponses[("/ConnectionManager/ctrl", "GetProtocolInfo")] = (
            200, _enveloppe("GetProtocolInfo", {"Source": "", "Sink": _x(sink)}, CM))
        self.etat = "NO_MEDIA_PRESENT"
        self.courante: tuple[str, float | None] | None = None  # (url, durée lue dans le DIDL)
        self.suivante: tuple[str, float | None] | None = None
        self.debut = 0.0
        self.position = 0.0
        self.enchaine = True
        self.refuser_suivante = False
        self.refus_play = 0  # nombre de `Play` refusés (l'ampli sort de veille)
        self.urls_refusees: set[str] = set()  # `Play` refusé (714) pour ces pistes
        self.demarrage_s = 0.0  # après `Play`, TRANSITIONING pendant ce temps
        self.pause_au_passage = 0.0  # en enchaînant, STOPPED pendant ce temps
        self._pret = 0.0  # fin de l'état d'attente (TRANSITIONING ou STOPPED de passage)
        self.reltime_zero = 0  # GetPositionInfo rend RelTime 0 ce nombre de fois (lu à la fin de piste)
        self.jouees: list[str] = []  # chaque début de lecture d'une URL
        # L'ampli coupe seul ces URL tant de secondes après PLAYING (R0 : SINET
        # ou un flux qu'il refuse), une fois chacune.
        self.arret_apres_s: dict[str, float] = {}

    # ── ce que fait le lecteur ──────────────────────────────────────────

    def _avancer(self) -> None:
        if self.etat in ("TRANSITIONING", "PASSAGE") and time.monotonic() >= self._pret:
            self.etat, self.debut = "PLAYING", self._pret
        while self.etat == "PLAYING" and self.courante is not None:
            coupe = self.arret_apres_s.get(self.courante[0])
            if coupe is not None and time.monotonic() - self.debut >= coupe:
                del self.arret_apres_s[self.courante[0]]
                self.etat, self.position = "STOPPED", 0.0
                return
            duree = self.courante[1]
            if duree is None or time.monotonic() - self.debut < duree:
                return
            if self.enchaine and self.suivante is not None:
                self.debut += duree
                self.courante, self.suivante = self.suivante, None
                self.jouees.append(self.courante[0])
                if self.pause_au_passage:
                    self.etat, self._pret = "PASSAGE", self.debut + self.pause_au_passage
                    self._avancer()
                    return
            else:
                self.etat, self.position = "STOPPED", 0.0

    def temps(self) -> float:
        self._avancer()
        if self.etat in ("TRANSITIONING", "PASSAGE"):
            return 0.0
        return time.monotonic() - self.debut if self.etat == "PLAYING" else self.position

    @property
    def etat_annonce(self) -> str:
        return "STOPPED" if self.etat == "PASSAGE" else self.etat

    # ── ce que fait quelqu'un d'autre ───────────────────────────────────

    def stop_externe(self) -> None:
        self._avancer()
        self.etat, self.position = "STOPPED", 0.0

    def pause_externe(self) -> None:
        self.position = self.temps()
        self.etat = "PAUSED_PLAYBACK"

    def jouer_autre(self, url: str) -> None:
        self.courante, self.suivante = (url, 600.0), None
        self.etat, self.debut = "PLAYING", time.monotonic()

    # ── le protocole ────────────────────────────────────────────────────

    @staticmethod
    def _duree(didl: str) -> float | None:
        m = re.search(r'duration="([^"]+)"', didl or "")
        return secondes(m[1]) if m else None

    def _repondre(self, r):
        statut, corps = super()._repondre(r)
        if r.chemin != "/AVTransport/ctrl" or not r.action:
            return statut, corps
        a = r.arguments or {}
        self._avancer()
        if r.action == "SetAVTransportURI":
            self.courante = (a.get("CurrentURI", ""), self._duree(a.get("CurrentURIMetaData", "")))
            self.suivante = None
            self.etat, self.position = "STOPPED", 0.0
        elif r.action == "SetNextAVTransportURI":
            if self.refuser_suivante:
                return 500, faute(701, "Transition not available")
            self.suivante = (a.get("NextURI", ""), self._duree(a.get("NextURIMetaData", "")))
        elif r.action == "Play":
            if self.refus_play > 0:
                self.refus_play -= 1
                return 500, faute(701, "Transition not available")
            if self.courante is None:
                return 500, faute(701, "Transition not available")
            if self.courante[0] in self.urls_refusees:
                return 500, faute(714, "Illegal MIME-type")
            if self.etat == "PAUSED_PLAYBACK":
                self.debut = time.monotonic() - self.position
                self.etat = "PLAYING"
            elif self.etat not in ("PLAYING", "TRANSITIONING"):
                self.jouees.append(self.courante[0])
                if self.demarrage_s:
                    self.etat, self._pret = "TRANSITIONING", time.monotonic() + self.demarrage_s
                else:
                    self.etat, self.debut = "PLAYING", time.monotonic()
        elif r.action == "Stop":
            self.etat, self.position = "STOPPED", 0.0
        elif r.action == "Pause":
            self.position = self.temps()
            self.etat = "PAUSED_PLAYBACK"
        elif r.action == "GetTransportInfo":
            return 200, _enveloppe("GetTransportInfo", {
                "CurrentTransportState": self.etat_annonce, "CurrentTransportStatus": "OK", "CurrentSpeed": "1"})
        elif r.action == "GetPositionInfo":
            url, duree = self.courante or ("", None)
            temps = self.temps()
            if self.reltime_zero > 0:
                self.reltime_zero -= 1
                temps = 0.0
            return 200, _enveloppe("GetPositionInfo", {
                "Track": "1" if url else "0", "TrackDuration": _temps(duree) if url else "0:00:00",
                "TrackMetaData": "", "TrackURI": _x(url), "RelTime": _temps(temps),
                "AbsTime": "NOT_IMPLEMENTED", "RelCount": "0", "AbsCount": "0"})
        elif r.action == "GetMediaInfo":
            return 200, _enveloppe("GetMediaInfo", {
                "CurrentURI": _x((self.courante or ("",))[0]), "NextURI": _x((self.suivante or ("",))[0])})
        return statut, corps

    def actions(self) -> list[str]:
        return [r.action for r in self.soaps]

    def uris(self, action: str) -> list[str]:
        cle = "NextURI" if action == "SetNextAVTransportURI" else "CurrentURI"
        return [r.arguments[cle] for r in self.soaps if r.action == action]


def ip_locale() -> str | None:
    """Une adresse non bouclée de cette machine : `adresse_reseau` refuse
    `127.0.0.1`, et une adresse locale sur un port fermé répond tout de
    suite (la vérification du réglage ne fait pas attendre 2 s)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))  # aucun paquet envoyé
            ip = s.getsockname()[0]
        except OSError:
            return None
    return None if ip.startswith("127.") else ip
