"""Le client DLNA contre un faux lecteur : un vrai serveur HTTP qui joue un DMR.

Les réponses viennent de l'AVR-X4000 (`fixtures/avrx4000/`, capturées en
lecture seule : `description.xml`, `GetProtocolInfo`, `GetTransportInfo`,
`GetPositionInfo` et une faute 718 ; numéro de série et UDN effacés). Le faux
lecteur vérifie le `SOAPACTION` de chaque requête contre l'action du corps.
"""

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest

from denon.backend.dlna import (
    DelaiDepasse,
    ErreurUpnp,
    LecteurDlna,
    LecteurInjoignable,
    ReponseInvalide,
    adresse_description,
    didl,
    duree_didl,
    lire_description,
    secondes,
)
from denon.tests.aides import port_libre

FIXTURES = Path(__file__).parent / "fixtures" / "avrx4000"
SOAP = "{http://schemas.xmlsoap.org/soap/envelope/}"
DIDL = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}"
DC = "{http://purl.org/dc/elements/1.1/}"
UPNP = "{urn:schemas-upnp-org:metadata-1-0/upnp/}"
AVT = "urn:schemas-upnp-org:service:AVTransport:1"


def fixture(nom: str) -> bytes:
    return (FIXTURES / nom).read_bytes()


FAUTE = fixture("GetTransportInfo-faute.xml").decode()


def faute(code: int, description: str) -> bytes:
    return FAUTE.replace("718", str(code)).replace("Invalid InstanceID", description).encode()


def reponse_vide(action: str, urn: str = AVT) -> bytes:
    return (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action}Response xmlns:u="{urn}"></u:{action}Response></s:Body></s:Envelope>'
    ).encode()


@dataclass
class Requete:
    methode: str
    chemin: str
    entetes: dict[str, str]
    corps: bytes
    service: str = ""  # URN tiré du SOAPACTION
    action: str = ""
    arguments: dict | None = None


class FauxLecteur:
    """Un DMR minimal sur HTTP/1.1 : la description et des réponses SOAP.

    `reponses[(chemin, action)]` rend `(statut, corps)` ; une action inconnue
    rend une faute 401. Le SOAPACTION doit nommer le même service et la même
    action que l'élément du corps, sinon la requête est refusée en 400.
    """

    def __init__(self, description: bytes | None = None):
        self.description = description if description is not None else fixture("description.xml")
        self.chemin_description = "/description.xml"
        self.reponses: dict[tuple[str, str], tuple[int, bytes]] = {
            ("/ConnectionManager/ctrl", "GetProtocolInfo"): (200, fixture("GetProtocolInfo.xml")),
            ("/AVTransport/ctrl", "GetTransportInfo"): (200, fixture("GetTransportInfo.xml")),
            ("/AVTransport/ctrl", "GetPositionInfo"): (200, fixture("GetPositionInfo.xml")),
        }
        for action in ("SetAVTransportURI", "SetNextAVTransportURI", "Play", "Pause", "Stop"):
            self.reponses[("/AVTransport/ctrl", action)] = (200, reponse_vide(action))
        self.requetes: list[Requete] = []
        self.refus: list[str] = []
        self.attente = 0.0  # avant de répondre, pour les délais
        self.serveur = None
        self.port = 0

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def soaps(self) -> list[Requete]:
        return [r for r in self.requetes if r.action]

    async def demarrer(self):
        self.serveur = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.serveur.sockets[0].getsockname()[1]

    async def arreter(self):
        self.serveur.close()
        self.serveur.close_clients()  # les connexions gardées ouvertes par httpx
        await self.serveur.wait_closed()

    async def _client(self, lecteur, ecrivain):
        try:
            while True:
                try:
                    tete = await lecteur.readuntil(b"\r\n\r\n")
                except (asyncio.IncompleteReadError, ConnectionError):
                    return
                ligne, *lignes = tete.decode("latin-1").split("\r\n")
                methode, chemin, _ = ligne.split(" ", 2)
                entetes = {}
                for l in lignes:
                    if ":" in l:
                        k, v = l.split(":", 1)
                        entetes[k.strip().lower()] = v.strip()
                corps = await lecteur.readexactly(int(entetes.get("content-length", 0)))
                statut, reponse = self._repondre(Requete(methode, chemin, entetes, corps))
                if self.attente:
                    await asyncio.sleep(self.attente)
                ecrivain.write(
                    f"HTTP/1.1 {statut} X\r\nCONTENT-TYPE: text/xml; charset=\"utf-8\"\r\n"
                    f"CONTENT-LENGTH: {len(reponse)}\r\nSERVER: KnOS/3.2 UPnP/1.0 DMP/3.5\r\n\r\n".encode() + reponse
                )
                await ecrivain.drain()
        finally:
            ecrivain.close()

    def _repondre(self, r: Requete) -> tuple[int, bytes]:
        self.requetes.append(r)
        if r.methode == "GET":
            return (200, self.description) if r.chemin == self.chemin_description else (404, b"")
        if r.methode != "POST":
            return 405, b""
        m = re.fullmatch(r'"([^"#]+)#(\w+)"', r.entetes.get("soapaction", ""))
        if not m or "text/xml" not in r.entetes.get("content-type", ""):
            self.refus.append(f"en-têtes : {r.entetes}")
            return 400, b""
        corps = ET.fromstring(r.corps).find(f"{SOAP}Body")[0]
        if corps.tag != f"{{{m[1]}}}{m[2]}":
            self.refus.append(f"SOAPACTION {m[0]} ≠ corps {corps.tag}")
            return 400, b""
        r.service, r.action = m[1], m[2]
        r.arguments = {c.tag: c.text or "" for c in corps}
        return self.reponses.get((r.chemin, r.action), (500, faute(401, "Invalid Action")))


@pytest.fixture
async def faux_lecteur():
    f = FauxLecteur()
    await f.demarrer()
    yield f
    await f.arreter()


@pytest.fixture
async def lecteur(faux_lecteur):
    async with LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=1) as l:
        yield l
    assert faux_lecteur.refus == []


@dataclass
class FauxFlux:
    """Les attributs de `FluxLecteur` (cœur 0.5) dont le client se sert."""

    url: str = "http://192.168.1.116:8090/api/flux/12/original"
    protocol_info: str = "http-get:*:audio/flac:DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
    titre: str = "Titre"
    artiste: str = "Artiste"
    album: str = "Album"
    duree: float | None = 214.907
    pochette: str | None = None


# ------------------------------------------------------------------ description


def test_adresse_par_defaut():
    assert adresse_description("192.168.1.184") == "http://192.168.1.184:8080/description.xml"


def test_description_de_l_avrx4000():
    s = lire_description(fixture("description.xml"), "http://192.168.1.184:8080/description.xml")
    assert (s.avtransport.type, s.avtransport.controle) == (AVT, "http://192.168.1.184:8080/AVTransport/ctrl")
    assert s.connexions.controle == "http://192.168.1.184:8080/ConnectionManager/ctrl"
    assert s.rendu.controle == "http://192.168.1.184:8080/RenderingControl/ctrl"


def _description(services: str, avant: str = "") -> str:
    return (
        '<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">'
        f"{avant}<device><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>"
        f"<serviceList>{services}</serviceList></device></root>"
    )


def _service(nom: str, controle: str, version: int = 1) -> str:
    return (f"<service><serviceType>urn:schemas-upnp-org:service:{nom}:{version}</serviceType>"
            f"<controlURL>{controle}</controlURL></service>")


def test_description_url_relatives_absolues_et_urlbase():
    xml = _description(
        _service("AVTransport", "upnp/avt", 2)  # relative au dossier de la description
        + _service("ConnectionManager", "http://10.0.0.9:49152/cm")  # absolue, autre hôte
    )
    s = lire_description(xml, "http://10.0.0.5:1400/xml/desc.xml")
    assert s.avtransport == type(s.avtransport)("urn:schemas-upnp-org:service:AVTransport:2", "http://10.0.0.5:1400/xml/upnp/avt")
    assert s.connexions.controle == "http://10.0.0.9:49152/cm"
    assert s.rendu is None
    avec_base = _description(_service("AVTransport", "/avt") + _service("ConnectionManager", "cm"),
                             avant="<URLBase>http://10.0.0.7:8000/base/</URLBase>")
    s = lire_description(avec_base, "http://10.0.0.5:1400/xml/desc.xml")
    assert (s.avtransport.controle, s.connexions.controle) == ("http://10.0.0.7:8000/avt", "http://10.0.0.7:8000/base/cm")


def test_description_dans_un_peripherique_imbrique():
    xml = _description("", avant="").replace(
        "<serviceList></serviceList>",
        "<deviceList><device><serviceList>" + _service("AVTransport", "/a") + _service("ConnectionManager", "/c")
        + "</serviceList></device></deviceList>",
    )
    assert lire_description(xml, "http://h/d.xml").avtransport.controle == "http://h/a"


def test_description_sans_avtransport_ou_illisible():
    with pytest.raises(ReponseInvalide, match="AVTransport"):
        lire_description(_description(_service("ConnectionManager", "/c")), "http://h/d.xml")
    with pytest.raises(ReponseInvalide, match="illisible"):
        lire_description("<root><device>", "http://h/d.xml")


async def test_description_lue_une_fois_et_chemins_pris_dans_la_description(faux_lecteur):
    # Les chemins ne sont pas codés en dur : on les déplace dans la description.
    faux_lecteur.description = fixture("description.xml").replace(b"/AVTransport/ctrl", b"autre/avt")
    faux_lecteur.chemin_description = "/dmr/description.xml"
    faux_lecteur.reponses[("/dmr/autre/avt", "GetTransportInfo")] = (200, fixture("GetTransportInfo.xml"))
    async with LecteurDlna(f"{faux_lecteur.base}/dmr/description.xml", delai=1) as l:
        await l.etat()
        await l.etat()
    assert [(r.methode, r.chemin) for r in faux_lecteur.requetes] == [
        ("GET", "/dmr/description.xml"), ("POST", "/dmr/autre/avt"), ("POST", "/dmr/autre/avt")]


async def test_adresse_relue_a_chaud(faux_lecteur):
    adresse = {"v": f"{faux_lecteur.base}/description.xml"}
    autre = FauxLecteur()
    await autre.demarrer()
    try:
        async with LecteurDlna(lambda: adresse["v"], delai=1) as l:
            await l.etat()
            adresse["v"] = f"{autre.base}/description.xml"
            await l.etat()
    finally:
        await autre.arreter()
    assert len(faux_lecteur.soaps) == 1 and len(autre.soaps) == 1


async def test_description_absente(faux_lecteur):
    async with LecteurDlna(f"{faux_lecteur.base}/rien.xml", delai=1) as l:
        with pytest.raises(ReponseInvalide, match="404"):
            await l.etat()


# ------------------------------------------------------------------ ConnectionManager


async def test_protocoles_de_l_avrx4000(lecteur, faux_lecteur):
    p = await lecteur.protocoles()
    assert len(p) == 17
    assert p[:2] == ["http-get:*:audio/L16;rate=44100;channels=1:DLNA.ORG_PN=LPCM",
                     "http-get:*:audio/L16;rate=44100;channels=2:DLNA.ORG_PN=LPCM"]
    assert "http-get:*:audio/flac:*" in p and "http-wavetunes:*:audio/x-ms-wma:*" in p
    assert p[-1] == "http-get:*:image/jpeg:*"
    (r,) = faux_lecteur.soaps
    assert (r.chemin, r.service, r.action, r.arguments) == (
        "/ConnectionManager/ctrl", "urn:schemas-upnp-org:service:ConnectionManager:1", "GetProtocolInfo", {})


async def test_protocoles_virgule_echappee_et_sink_vide(lecteur, faux_lecteur):
    cle = ("/ConnectionManager/ctrl", "GetProtocolInfo")
    faux_lecteur.reponses[cle] = (200, fixture("GetProtocolInfo.xml").replace(
        b"<Sink>", b"<Sink>http-get:*:audio/x-a:A\\,B , ,"))
    p = await lecteur.protocoles()
    assert p[0] == "http-get:*:audio/x-a:A\\,B" and len(p) == 18
    faux_lecteur.reponses[cle] = (200, re.sub(rb"<Sink>.*</Sink>", b"<Sink/>", fixture("GetProtocolInfo.xml")))
    assert await lecteur.protocoles() == []


# ------------------------------------------------------------------ AVTransport


async def test_etat_et_position_de_l_avrx4000(lecteur, faux_lecteur):
    e = await lecteur.etat()
    assert (e.etat, e.statut, e.vitesse) == ("NO_MEDIA_PRESENT", "OK", "1")
    p = await lecteur.position()
    assert (p.uri, p.temps, p.duree, p.temps_s, p.duree_s) == ("", "0:00:00", "0:00:00", 0, 0)
    assert [r.arguments for r in faux_lecteur.soaps] == [{"InstanceID": "0"}] * 2


async def test_position_en_lecture(lecteur, faux_lecteur):
    faux_lecteur.reponses[("/AVTransport/ctrl", "GetPositionInfo")] = (200, fixture("GetPositionInfo.xml")
        .replace(b"<TrackURI></TrackURI>", b"<TrackURI>http://u/api/flux/1/original?a=1&amp;b=2</TrackURI>")
        .replace(b"<RelTime>0:00:00", b"<RelTime>0:01:23")
        .replace(b"<TrackDuration>0:00:00", b"<TrackDuration>0:03:34.907"))
    p = await lecteur.position()
    assert p.uri == "http://u/api/flux/1/original?a=1&b=2"
    assert (p.temps_s, p.duree_s) == (83, pytest.approx(214.907))


def test_secondes():
    assert secondes("1:02:03.5") == 3723.5
    assert secondes("NOT_IMPLEMENTED") is None and secondes("") is None


async def test_commandes_de_transport(lecteur, faux_lecteur):
    await lecteur.jouer()
    await lecteur.pause()
    await lecteur.arreter()
    assert [(r.action, r.arguments) for r in faux_lecteur.soaps] == [
        ("Play", {"InstanceID": "0", "Speed": "1"}), ("Pause", {"InstanceID": "0"}), ("Stop", {"InstanceID": "0"})]
    assert {r.entetes["soapaction"] for r in faux_lecteur.soaps} == {f'"{AVT}#Play"', f'"{AVT}#Pause"', f'"{AVT}#Stop"'}


async def test_definir_uri_et_suivante(lecteur, faux_lecteur):
    flux = FauxFlux(url="http://192.168.1.116:8090/api/flux/12/original?x=1&y=2")
    await lecteur.definir_uri(flux)
    await lecteur.definir_suivante(FauxFlux(url="http://h/api/flux/13/l16-44100"))
    uri, suivante = faux_lecteur.soaps
    assert uri.action == "SetAVTransportURI"
    assert uri.arguments["CurrentURI"] == flux.url  # le « & » a survécu à l'échappement
    assert uri.arguments["CurrentURIMetaData"] == didl(flux)
    assert suivante.action == "SetNextAVTransportURI"
    assert suivante.arguments["NextURI"] == "http://h/api/flux/13/l16-44100"
    assert ET.fromstring(suivante.arguments["NextURIMetaData"]).find(f"{DIDL}item/{DIDL}res").text == "http://h/api/flux/13/l16-44100"


# ------------------------------------------------------------------ DIDL-Lite


async def test_didl_echappe_deux_fois(lecteur, faux_lecteur):
    flux = FauxFlux(
        url="http://h/api/flux/1/original?a=1&b=<2>",
        titre='Rock & Roll <live> "été" l\'œuvre',
        artiste="Rocé & Cie",
        album="Identité en crescendo <deluxe>",
        pochette="http://h/api/pochette/1?t=1&s=480",
        duree=3723.4567,
    )
    await lecteur.definir_uri(flux)
    (r,) = faux_lecteur.soaps
    # Dans le SOAP, le DIDL est du texte : pas une balise brute dans le corps.
    assert b"<DIDL-Lite" not in r.corps and b"&lt;DIDL-Lite" in r.corps
    item = ET.fromstring(r.arguments["CurrentURIMetaData"]).find(f"{DIDL}item")
    assert item.find(f"{DC}title").text == 'Rock & Roll <live> "été" l\'œuvre'
    assert item.find(f"{DC}creator").text == "Rocé & Cie"
    assert item.find(f"{UPNP}artist").text == "Rocé & Cie"
    assert item.find(f"{UPNP}album").text == "Identité en crescendo <deluxe>"
    assert item.find(f"{UPNP}albumArtURI").text == "http://h/api/pochette/1?t=1&s=480"
    assert item.find(f"{UPNP}class").text == "object.item.audioItem.musicTrack"
    res = item.find(f"{DIDL}res")
    assert res.text == flux.url
    assert res.get("protocolInfo") == flux.protocol_info
    assert res.get("duration") == "1:02:03.457"


def test_didl_sans_pochette_ni_duree_ni_artiste():
    racine = ET.fromstring(didl(FauxFlux(pochette=None, duree=None, artiste="", album="")))
    item = racine.find(f"{DIDL}item")
    assert item.find(f"{UPNP}albumArtURI") is None and item.find(f"{UPNP}artist") is None
    assert item.find(f"{UPNP}album") is None
    assert item.find(f"{DIDL}res").get("duration") is None


def test_didl_retire_les_caracteres_interdits():
    titre = ET.fromstring(didl(FauxFlux(titre="a\x00b\x1fc\td"))).find(f"{DIDL}item/{DC}title").text
    assert titre == "abc\td"


def test_duree_didl():
    assert duree_didl(0) == "0:00:00.000"
    assert duree_didl(214.9066670) == "0:03:34.907"
    assert duree_didl(59.9996) == "0:01:00.000"
    assert duree_didl(36000) == "10:00:00.000"


# ------------------------------------------------------------------ erreurs


@pytest.mark.parametrize("code,description", [(701, "Transition not available"), (714, "Illegal MIME-type"), (716, "Resource not found")])
async def test_faute_soap(lecteur, faux_lecteur, code, description):
    faux_lecteur.reponses[("/AVTransport/ctrl", "SetAVTransportURI")] = (500, faute(code, description))
    with pytest.raises(ErreurUpnp) as e:
        await lecteur.definir_uri(FauxFlux())
    assert (e.value.code, e.value.description) == (code, description)


async def test_faute_reelle_de_l_avrx4000(lecteur, faux_lecteur):
    faux_lecteur.reponses[("/AVTransport/ctrl", "GetTransportInfo")] = (500, fixture("GetTransportInfo-faute.xml"))
    with pytest.raises(ErreurUpnp, match="718") as e:
        await lecteur.etat()
    assert e.value.description == "Invalid InstanceID"


async def test_erreur_http_sans_faute(lecteur, faux_lecteur):
    faux_lecteur.reponses[("/AVTransport/ctrl", "Play")] = (503, b"occupe")
    with pytest.raises(ReponseInvalide, match="503"):
        await lecteur.jouer()


async def test_delai_depasse(faux_lecteur):
    faux_lecteur.attente = 2
    async with LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=0.2) as l:
        t = time.monotonic()
        with pytest.raises(DelaiDepasse):
            await l.etat()
        assert time.monotonic() - t < 1


async def test_delai_depasse_sur_une_reponse_qui_goutte():
    """Un délai borne tout l'appel, pas chaque octet : un lecteur qui envoie
    un octet toutes les 0,1 s est coupé quand même."""

    async def goutte(lecteur, ecrivain):
        await lecteur.readuntil(b"\r\n\r\n")
        ecrivain.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
        try:
            for _ in range(100):
                ecrivain.write(b" ")
                await ecrivain.drain()
                await asyncio.sleep(0.1)
        except ConnectionError:
            pass
        finally:
            ecrivain.close()

    serveur = await asyncio.start_server(goutte, "127.0.0.1", 0)
    port = serveur.sockets[0].getsockname()[1]
    try:
        async with LecteurDlna(f"http://127.0.0.1:{port}/description.xml", delai=0.5) as l:
            t = time.monotonic()
            with pytest.raises(DelaiDepasse):
                await l.services()
            assert time.monotonic() - t < 1.5
    finally:
        serveur.close()
        await serveur.wait_closed()


async def test_lecteur_injoignable():
    async with LecteurDlna(adresse_description("127.0.0.1", port_libre()), delai=1) as l:
        with pytest.raises(LecteurInjoignable) as e:
            await l.protocoles()
    assert not isinstance(e.value, DelaiDepasse)


async def test_injoignable_en_cours_de_route_relit_la_description(faux_lecteur):
    async with LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=1) as l:
        await l.etat()
        port = faux_lecteur.port
        await faux_lecteur.arreter()
        with pytest.raises(LecteurInjoignable):
            await l.etat()
        # L'ampli revient (redémarrage) : la description est relue.
        faux_lecteur.serveur = await asyncio.start_server(faux_lecteur._client, "127.0.0.1", port)
        await l.etat()
    assert [r.methode for r in faux_lecteur.requetes] == ["GET", "POST", "GET", "POST"]
