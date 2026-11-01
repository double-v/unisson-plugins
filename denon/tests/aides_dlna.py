"""Le faux lecteur DLNA des tests : un vrai serveur HTTP qui joue un DMR.

Les réponses viennent de l'AVR-X4000 (`fixtures/avrx4000/`). Le faux lecteur
vérifie le `SOAPACTION` de chaque requête contre l'action du corps. Partagé
par `test_dlna.py` et le DMR à états de la séance (`aides_seance.py`).
"""

import asyncio
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

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
            ("/AVTransport/ctrl", "GetMediaInfo"): (200, fixture("GetMediaInfo.xml")),
        }
        for action in ("SetAVTransportURI", "SetNextAVTransportURI", "Play", "Pause", "Stop"):
            self.reponses[("/AVTransport/ctrl", action)] = (200, reponse_vide(action))
        self.requetes: list[Requete] = []
        self.refus: list[str] = []
        self.attente = 0.0  # avant de répondre, pour les délais
        self.attentes: dict[str, float] = {}  # par méthode HTTP (« GET », « POST »)
        self.serveur = None
        self.port = 0
        self.ouvertes = 0  # connexions HTTP ouvertes en ce moment

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
        self.ouvertes += 1
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
                if attente := self.attentes.get(methode, self.attente):
                    await asyncio.sleep(attente)
                ecrivain.write(
                    f"HTTP/1.1 {statut} X\r\nCONTENT-TYPE: text/xml; charset=\"utf-8\"\r\n"
                    f"CONTENT-LENGTH: {len(reponse)}\r\nSERVER: KnOS/3.2 UPnP/1.0 DMP/3.5\r\n\r\n".encode() + reponse
                )
                await ecrivain.drain()
        finally:
            self.ouvertes -= 1
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
