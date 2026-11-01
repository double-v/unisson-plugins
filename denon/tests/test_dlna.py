"""Le client DLNA contre un faux lecteur : un vrai serveur HTTP qui joue un DMR.

Les réponses viennent de l'AVR-X4000 (`fixtures/avrx4000/`, capturées en
lecture seule : `description.xml`, `GetProtocolInfo`, `GetTransportInfo`,
`GetPositionInfo`, `GetMediaInfo` (mal formé) et une faute 718 ; numéro de
série et UDN effacés). Le faux
lecteur vérifie le `SOAPACTION` de chaque requête contre l'action du corps.
"""

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from denon.backend.dlna import (
    DelaiDepasse,
    champ,
    entites_xml,
    meme_piste,
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
from denon.tests.aides_dlna import (  # noqa: F401
    AVT, DC, DIDL, FAUTE, FIXTURES, SOAP, UPNP, FauxLecteur, Requete, faute, fixture, reponse_vide,
)


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


# ------------------------------------------------------------------ adresses invalides


@pytest.mark.parametrize("adresse", [
    "http://127.0.0.1:80800/description.xml",  # port impossible
    "http://[::1/description.xml",  # crochet non fermé
    "ftp://127.0.0.1/description.xml",
    "http:///description.xml",  # pas d'hôte
    "description.xml",
])
async def test_adresse_de_description_invalide(adresse):
    async with LecteurDlna(adresse, delai=1) as l:
        with pytest.raises(ReponseInvalide, match="adresse invalide"):
            await l.etat()


async def test_url_de_controle_invalide_dans_la_description(faux_lecteur):
    faux_lecteur.description = fixture("description.xml").replace(b"/AVTransport/ctrl", b"http://127.0.0.1:99999/avt")
    async with LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=1) as l:
        with pytest.raises(ReponseInvalide, match="99999"):
            await l.jouer()


async def test_fonction_d_adresse_qui_echoue():
    def adresse():
        raise KeyError("hote")

    async with LecteurDlna(adresse, delai=1) as l:
        with pytest.raises(ReponseInvalide):
            await l.protocoles()


async def test_client_externe_ferme(faux_lecteur):
    client = httpx.AsyncClient()
    await client.aclose()
    l = LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=1, client=client)
    with pytest.raises(LecteurInjoignable, match="inutilisable"):
        await l.etat()


# ------------------------------------------------------------------ délai par appel public


async def test_delai_borne_description_et_soap_ensemble(faux_lecteur):
    """La description et le POST tiennent chacun dans le délai, pas les deux
    ensemble : l'appel public est coupé quand même."""
    faux_lecteur.attentes = {"GET": 0.3, "POST": 0.3}
    async with LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=0.5) as l:
        t = time.monotonic()
        with pytest.raises(DelaiDepasse):
            await l.definir_uri(FauxFlux())
        assert time.monotonic() - t < 0.75


async def test_delai_sur_le_seul_post_soap(faux_lecteur):
    faux_lecteur.attentes = {"POST": 0.6}  # la description répond tout de suite
    async with LecteurDlna(f"{faux_lecteur.base}/description.xml", delai=0.5) as l:
        t = time.monotonic()
        with pytest.raises(DelaiDepasse):
            await l.etat()
        assert time.monotonic() - t < 0.75
    assert [r.methode for r in faux_lecteur.requetes] == ["GET", "POST"]


# ------------------------------------------------------------------ GetMediaInfo


async def test_media_de_l_avrx4000_malforme(lecteur, faux_lecteur):
    """La réponse réelle : un NextURI qui contient un DIDL brut et tronqué, ce
    qui n'est pas du XML bien formé. Les autres champs se lisent quand même."""
    brut = fixture("GetMediaInfo.xml")
    with pytest.raises(ET.ParseError):
        ET.fromstring(brut)
    m = await lecteur.media()
    assert m.uri == ""
    assert m.suivante.startswith("<DIDL-Lite") and m.suivante.endswith("<upnp:class>object")
    texte = brut.decode()
    assert champ(texte, "PlayMedium") == "NONE"
    assert champ(texte, "NextURIMetaData").startswith('<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"')


async def test_media_current_uri_distinct_de_ses_metadonnees(lecteur, faux_lecteur):
    meta = didl(FauxFlux(url="http://h/api/flux/9/original"))
    echappe = meta.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    corps = (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        f'<u:GetMediaInfoResponse xmlns:u="{AVT}"><NrTracks>1</NrTracks>'
        f"<CurrentURIMetaData>{echappe}</CurrentURIMetaData>"  # avant CurrentURI, exprès
        "<CurrentURI>http://h/api/flux/9/original?a=1&amp;b=2</CurrentURI>"
        "<NextURI></NextURI><NextURIMetaData></NextURIMetaData>"
        "</u:GetMediaInfoResponse></s:Body></s:Envelope>"
    )
    faux_lecteur.reponses[("/AVTransport/ctrl", "GetMediaInfo")] = (200, corps.encode())
    m = await lecteur.media()
    assert (m.uri, m.suivante) == ("http://h/api/flux/9/original?a=1&b=2", "")
    assert champ(corps, "CurrentURIMetaData") == meta


# ------------------------------------------------------------------ champ()


def test_champ_prefixe_d_un_namespace():
    xml = '<u:R xmlns:u="x" xmlns:m="y"><m:Sink a="1">http-get:*:audio/flac:*</m:Sink></u:R>'
    assert champ(xml, "Sink") == "http-get:*:audio/flac:*"
    assert champ(xml, "Source") is None


def test_champ_auto_fermant_ne_deborde_pas():
    assert champ('<X a="b"/><Y>1</Y><X>2</X>', "X") == "2"
    assert champ('<X a="b"/><Y>1</Y>', "X") == ""
    assert champ("<X/>", "X") == ""


def test_champ_decode_les_seules_entites_xml():
    xml = "<A>&lt;b&gt; &amp;eacute; &eacute; &quot;&apos; &#233;&#xE9;&#X41;</A>"
    assert champ(xml, "A") == "<b> &eacute; &eacute; \"' ééA"
    assert entites_xml("&#99999999999;") == "&#99999999999;"


# ------------------------------------------------------------------ secondes, meme_piste


def test_secondes_fraction_f0_f1():
    assert secondes("0:00:01.1/4") == 1.25
    assert secondes("1:00:00.0/3") == 3600
    assert secondes("0:00:01.4/4") is None and secondes("0:00:01.1/0") is None


@pytest.mark.parametrize("a,b,egales", [
    ("http://H.local:80/api/flux/1/original", "HTTP://h.local/api/flux/1/original", True),
    ("http://h/api/flux/1/original?x=%7e", "http://h/api/flux/1/original?x=~", True),
    ("http://h/a%2fb", "http://h/a%2Fb", True),
    ("http://h/a%2Fb", "http://h/a/b", False),  # « / » réservé : pas le même chemin
    ("http://h/api/flux/1", "http://h/api/flux/1#x", True),
    ("http://h", "http://h/", True),
    ("http://h/api/flux/1/Original", "http://h/api/flux/1/original", False),
    ("http://h/api/flux/1?a=1&b=2", "http://h/api/flux/1?b=2&a=1", False),
    ("http://h:8090/api/flux/1", "http://h/api/flux/1", False),
    ("https://h/api/flux/1", "https://h:443/api/flux/1", True),
    ("", "", False),
    ("http://[::1/x", "http://[::1/x", False),
])
def test_meme_piste(a, b, egales):
    assert meme_piste(a, b) is egales


# ------------------------------------------------------------------ cas limites du DIDL


@pytest.mark.parametrize("duree", [float("nan"), float("inf"), float("-inf")])
def test_didl_duree_non_finie_omise(duree):
    res = ET.fromstring(didl(FauxFlux(duree=duree))).find(f"{DIDL}item/{DIDL}res")
    assert res.get("duration") is None


async def test_didl_retire_les_surrogates_isoles(lecteur, faux_lecteur):
    flux = FauxFlux(titre="a\ud800b\udfffc")
    assert ET.fromstring(didl(flux)).find(f"{DIDL}item/{DC}title").text == "abc"
    await lecteur.definir_uri(flux)  # la requête s'encode en UTF-8
    (r,) = faux_lecteur.soaps
    assert "<dc:title>abc</dc:title>" in r.arguments["CurrentURIMetaData"]
