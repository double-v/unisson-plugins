"""Client UPnP/DLNA d'un lecteur réseau (DMR), sans rien de propre à Denon.

Il lit la description du lecteur (`description.xml`) pour trouver les URL de
contrôle d'AVTransport, de ConnectionManager et de RenderingControl, puis
envoie les actions SOAP dont le réveil a besoin. Ce module n'importe pas
`unisson.plugin` : il se teste seul, contre un vrai serveur HTTP.

Pièges relevés sur l'AVR-X4000 (puce BridgeCo, serveur `KnOS/3.2`) :

- les réponses n'ont pas de déclaration XML, et certaines ne sont pas du XML
  bien formé (`GetMediaInfo` rend un `NextURI` avec un DIDL non échappé et
  tronqué). Les champs des réponses sont donc lus un par un, par motif,
  plutôt que par un analyseur XML qui refuserait tout le document ;
- une faute SOAP arrive en HTTP 500 avec un `UPnPError` (`errorCode`,
  `errorDescription`) ;
- `GetTransportInfo` répond aussi en veille : il ne prouve pas que l'ampli
  est prêt à jouer.

Les flux passés à `definir_uri` et `definir_suivante` sont des objets qui ont
les attributs de `FluxLecteur` (cœur 0.5) : `url`, `protocol_info`, `titre`,
`artiste`, `album`, `duree`, `pochette`.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

PORT_UPNP = 8080
DELAI_S = 5.0

AVTRANSPORT = "AVTransport"
CONNEXIONS = "ConnectionManager"
RENDU = "RenderingControl"


def adresse_description(hote: str, port: int = PORT_UPNP) -> str:
    """L'emplacement par défaut de la description : `http://<hôte>:8080/description.xml`."""
    return f"http://{hote}:{port}/description.xml"


# ------------------------------------------------------------------ erreurs


class ErreurDlna(Exception):
    """Toute erreur du client DLNA."""


class LecteurInjoignable(ErreurDlna):
    """Le lecteur ne répond pas : refus de connexion, réseau, hôte inconnu."""


class DelaiDepasse(LecteurInjoignable):
    """Le lecteur n'a pas répondu dans le délai."""


class ReponseInvalide(ErreurDlna):
    """Le lecteur répond, mais pas ce qu'on attend (statut HTTP, service absent)."""


class ErreurUpnp(ErreurDlna):
    """Une faute SOAP (`UPnPError`) rendue par le lecteur."""

    def __init__(self, code: int, description: str):
        super().__init__(f"UPnP {code} : {description}")
        self.code = code
        self.description = description


# ------------------------------------------------------------------ données


class Flux(Protocol):
    url: str
    protocol_info: str
    titre: str
    artiste: str
    album: str
    duree: float | None
    pochette: str | None


@dataclass(frozen=True)
class Service:
    type: str  # URN complet, ex. « urn:schemas-upnp-org:service:AVTransport:1 »
    controle: str  # URL absolue de contrôle


@dataclass(frozen=True)
class Services:
    avtransport: Service
    connexions: Service
    rendu: Service | None  # RenderingControl, facultatif pour le réveil


@dataclass(frozen=True)
class EtatTransport:
    etat: str  # PLAYING, STOPPED, PAUSED_PLAYBACK, TRANSITIONING, NO_MEDIA_PRESENT
    statut: str  # OK, ERROR_OCCURRED
    vitesse: str


@dataclass(frozen=True)
class Position:
    uri: str  # TrackURI : la piste en cours, vide s'il n'y en a pas
    temps: str  # RelTime tel quel, ex. « 0:01:23 »
    duree: str  # TrackDuration tel quel

    @property
    def temps_s(self) -> float | None:
        return secondes(self.temps)

    @property
    def duree_s(self) -> float | None:
        return secondes(self.duree)


def secondes(temps: str) -> float | None:
    """`H:MM:SS[.fff]` en secondes ; None pour `NOT_IMPLEMENTED` ou vide."""
    m = re.fullmatch(r"\s*(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s*", temps or "")
    if not m:
        return None
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def duree_didl(s: float) -> str:
    """Secondes en `H:MM:SS.mmm`, le format de l'attribut `duration` du DIDL."""
    ms = max(0, round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s_, ms = divmod(ms, 1000)
    return f"{h}:{m:02}:{s_:02}.{ms:03}"


# ------------------------------------------------------------------ XML

# Caractères interdits en XML 1.0 (une étiquette peut en contenir).
_INTERDITS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _x(texte: object) -> str:
    """Échappe pour un texte ou un attribut XML entre guillemets."""
    s = _INTERDITS.sub("", str(texte))
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def didl(flux: Flux) -> str:
    """Le DIDL-Lite d'une piste, à mettre (échappé une fois de plus par SOAP)
    dans `CurrentURIMetaData` ou `NextURIMetaData`."""
    item_id = "unisson-" + hashlib.sha1(flux.url.encode()).hexdigest()[:16]
    morceaux = [
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
        ' xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">',
        f'<item id="{item_id}" parentID="0" restricted="1">',
        f"<dc:title>{_x(flux.titre or flux.url)}</dc:title>",
    ]
    if flux.artiste:
        morceaux += [f"<dc:creator>{_x(flux.artiste)}</dc:creator>", f"<upnp:artist>{_x(flux.artiste)}</upnp:artist>"]
    if flux.album:
        morceaux.append(f"<upnp:album>{_x(flux.album)}</upnp:album>")
    if flux.pochette:
        morceaux.append(f"<upnp:albumArtURI>{_x(flux.pochette)}</upnp:albumArtURI>")
    morceaux.append("<upnp:class>object.item.audioItem.musicTrack</upnp:class>")
    duree = f' duration="{duree_didl(flux.duree)}"' if flux.duree is not None else ""
    morceaux.append(f'<res protocolInfo="{_x(flux.protocol_info)}"{duree}>{_x(flux.url)}</res>')
    morceaux.append("</item></DIDL-Lite>")
    return "".join(morceaux)


def _local(balise: str) -> str:
    return balise.rsplit("}", 1)[-1]


def lire_description(xml: bytes | str, adresse: str) -> Services:
    """Les services d'une description de périphérique UPnP.

    Les URL relatives se résolvent sur `URLBase` s'il existe, sinon sur
    l'adresse de la description. Les périphériques imbriqués sont parcourus.
    """
    try:
        racine = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ReponseInvalide(f"description illisible ({adresse}) : {e}") from e
    base = adresse
    for el in racine.iter():
        if _local(el.tag) == "URLBase" and (el.text or "").strip():
            base = el.text.strip()
    trouves: dict[str, Service] = {}
    for el in racine.iter():
        if _local(el.tag) != "service":
            continue
        champs = {_local(c.tag): (c.text or "").strip() for c in el}
        urn, controle = champs.get("serviceType", ""), champs.get("controlURL", "")
        m = re.fullmatch(r"urn:schemas-upnp-org:service:(\w+):\d+", urn)
        if m and controle and m[1] not in trouves:
            trouves[m[1]] = Service(urn, urljoin(base, controle))
    manquants = [n for n in (AVTRANSPORT, CONNEXIONS) if n not in trouves]
    if manquants:
        raise ReponseInvalide(f"service absent de la description ({adresse}) : {', '.join(manquants)}")
    return Services(trouves[AVTRANSPORT], trouves[CONNEXIONS], trouves.get(RENDU))


def champ(xml: str, nom: str) -> str | None:
    """La valeur d'un champ de réponse, déséchappée ; None s'il manque.

    Lu par motif et non par un analyseur XML : voir le docstring du module.
    """
    m = re.search(rf"<(?:[\w.-]+:)?{nom}(?:\s[^>]*)?(?:/>|>(.*?)</(?:[\w.-]+:)?{nom}\s*>)", xml, re.S)
    if not m:
        return None
    return unescape(m[1] or "")


def decouper_protocoles(sink: str) -> list[str]:
    """La liste `Sink` de `GetProtocolInfo`, découpée sur les virgules non
    échappées (`\\,` est une virgule dans une chaîne), chaque chaîne telle quelle."""
    return [p.strip() for p in re.split(r"(?<!\\),", sink) if p.strip()]


# ------------------------------------------------------------------ client


class LecteurDlna:
    """Un lecteur DLNA DMR piloté en SOAP.

    `description` est l'URL de `description.xml`, ou une fonction qui la rend
    (relue à chaque appel : un réglage changé à chaud est pris en compte).
    Chaque appel est borné par `delai` secondes, connexion comprise.
    """

    def __init__(self, description: str | Callable[[], str], *, delai: float = DELAI_S, client: httpx.AsyncClient | None = None):
        self._description = description if callable(description) else (lambda: description)
        self.delai = delai
        self._client = client
        self._propre = client is None
        self._services: tuple[str, Services] | None = None

    async def __aenter__(self) -> LecteurDlna:
        return self

    async def __aexit__(self, *_) -> None:
        await self.fermer()

    async def fermer(self) -> None:
        if self._propre and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.delai, follow_redirects=False)
        return self._client

    async def _requete(self, methode: str, url: str, **k) -> httpx.Response:
        hote = urlsplit(url).netloc
        try:
            async with asyncio.timeout(self.delai):
                return await self._http().request(methode, url, **k)
        except (TimeoutError, httpx.TimeoutException) as e:
            raise DelaiDepasse(f"le lecteur {hote} n'a pas répondu en {self.delai:g} s") from e
        except httpx.HTTPError as e:  # refus, réseau, nom inconnu, connexion coupée
            raise LecteurInjoignable(f"le lecteur {hote} est injoignable : {e!r}") from e

    # ---- description

    async def services(self) -> Services:
        """Les services du lecteur, lus une fois par adresse de description."""
        adresse = self._description()
        if self._services and self._services[0] == adresse:
            return self._services[1]
        r = await self._requete("GET", adresse)
        if r.status_code != 200:
            raise ReponseInvalide(f"description : HTTP {r.status_code} ({adresse})")
        services = lire_description(r.content, adresse)
        self._services = (adresse, services)
        return services

    # ---- SOAP

    async def soap(self, service: Service, action: str, arguments: dict[str, str] | None = None) -> str:
        """Envoie une action ; rend le corps de la réponse (texte brut).

        Les valeurs des arguments sont échappées ici : un DIDL-Lite se passe
        donc tel que `didl()` le rend.
        """
        args = "".join(f"<{k}>{_x(v)}</{k}>" for k, v in (arguments or {}).items())
        enveloppe = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{service.type}">{args}</u:{action}>'
            "</s:Body></s:Envelope>"
        )
        entetes = {"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{service.type}#{action}"'}
        try:
            r = await self._requete("POST", service.controle, content=enveloppe.encode(), headers=entetes)
        except LecteurInjoignable:
            self._services = None  # l'ampli a pu redémarrer : on relira sa description
            raise
        texte = r.content.decode("utf-8", "replace")
        code = champ(texte, "errorCode")
        if code is not None:
            try:
                n = int(code.strip())
            except ValueError:
                n = 0
            raise ErreurUpnp(n, (champ(texte, "errorDescription") or "").strip())
        if r.status_code != 200:
            raise ReponseInvalide(f"{action} : HTTP {r.status_code}")
        return texte

    async def _avt(self, action: str, **arguments: str) -> str:
        s = await self.services()
        return await self.soap(s.avtransport, action, {"InstanceID": "0", **arguments})

    # ---- ConnectionManager

    async def protocoles(self) -> list[str]:
        """Les chaînes protocolInfo `Sink` du lecteur, telles quelles."""
        s = await self.services()
        reponse = await self.soap(s.connexions, "GetProtocolInfo")
        sink = champ(reponse, "Sink")
        if sink is None:
            raise ReponseInvalide("GetProtocolInfo : pas de champ Sink")
        return decouper_protocoles(sink)

    # ---- AVTransport

    async def definir_uri(self, flux: Flux) -> None:
        await self._avt("SetAVTransportURI", CurrentURI=flux.url, CurrentURIMetaData=didl(flux))

    async def definir_suivante(self, flux: Flux) -> None:
        await self._avt("SetNextAVTransportURI", NextURI=flux.url, NextURIMetaData=didl(flux))

    async def jouer(self) -> None:
        await self._avt("Play", Speed="1")

    async def pause(self) -> None:
        await self._avt("Pause")

    async def arreter(self) -> None:
        await self._avt("Stop")

    async def etat(self) -> EtatTransport:
        r = await self._avt("GetTransportInfo")
        etat = champ(r, "CurrentTransportState")
        if not etat:
            raise ReponseInvalide("GetTransportInfo : pas de CurrentTransportState")
        return EtatTransport(etat.strip(), (champ(r, "CurrentTransportStatus") or "").strip(), (champ(r, "CurrentSpeed") or "").strip())

    async def position(self) -> Position:
        r = await self._avt("GetPositionInfo")
        return Position(
            (champ(r, "TrackURI") or "").strip(),
            (champ(r, "RelTime") or "").strip(),
            (champ(r, "TrackDuration") or "").strip(),
        )
