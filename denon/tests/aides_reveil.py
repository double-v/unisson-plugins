"""Les aides partagées des tests du réveil (`test_reveil*.py`)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from denon.backend import alarmes
from denon.backend.ordonnanceur import Ordonnanceur

PARIS = ZoneInfo("Europe/Paris")
UTC = timezone.utc
JETON = "jeton-de-test"
AUTH = {"Authorization": f"Bearer {JETON}"}
LOCAL = {"Host": "localhost", "Origin": "http://localhost"}
RACINE = "/api/plugins/denon/reveil"


async def regler(client, **valeurs):
    r = await client.put("/api/plugins/denon/settings", json=valeurs, headers=LOCAL)
    assert r.status_code == 200, r.text


def alarme(**champs) -> dict:
    return {"nom": "Semaine", "heure": "07:00", "jours": 31, "contexte": "bibliotheque", **champs}


class Horloge:
    def __init__(self, depart: datetime):
        self.t = depart

    def __call__(self) -> datetime:
        return self.t


def ordonnanceur(session, horloge, appels=None) -> Ordonnanceur:
    async def declencher(a):
        if appels is not None:
            appels.append((a["id"], horloge()))
        return "declenchee"

    return Ordonnanceur(session, lambda: PARIS, declencher=declencher, maintenant=horloge)


async def poser(session, horloge, **champs) -> dict:
    async with session() as s:
        a = await alarmes.creer(s, alarmes.valider(alarme(**champs)), horloge())
        await s.commit()
    return a


async def relire(session, ident) -> dict | None:
    async with session() as s:
        return await alarmes.lire(s, ident)


def a_paris(texte: str) -> datetime:
    return datetime.fromisoformat(texte).replace(tzinfo=PARIS).astimezone(UTC)


def dans(secondes: float) -> str:
    return (datetime.now(PARIS) + timedelta(seconds=secondes)).strftime("%H:%M:%S")


async def lire_alarme(client, ident) -> dict:
    return next(a for a in (await client.get(f"{RACINE}/alarmes", headers=AUTH)).json()["alarmes"] if a["id"] == ident)
