"""Le flux d'événements (`GET /api/events`, Server-Sent Events), de bout en
bout : HTTP réel → routeur → lien → faux ampli TCP.

Un client (la prise du caisson qui suit l'ampli) apprend chaque changement
d'état sans interroger `/api/state` en boucle : l'état complet à la
connexion, puis un état complet à chaque changement, connexion et coupure
du lien comprises, et un battement de cœur pour repérer une connexion morte.
"""

import asyncio
import json
import logging

import httpx
import pytest

from denon.backend import ecoute, routes
from denon.backend.lien import Config, Lien
from denon.backend.pilotes import PILOTES

from denon.tests.aides import attendre, port_libre

JETON = "secret-local"
BATTEMENT = 0.2


@pytest.fixture
async def flux(faux_ampli):
    lien = Lien(lambda: Config("127.0.0.1", faux_ampli.port, 0.01), PILOTES["avrx4000"], attente_min=0.05, attente_max=0.2)
    port = port_libre()
    routeur = routes.fabriquer(lien, lambda: JETON, battement_s=BATTEMENT)
    taches = [
        asyncio.create_task(lien.tourner()),
        asyncio.create_task(ecoute.servir(routeur, port, logging.getLogger("t"), "127.0.0.1")),
    ]
    await attendre(lambda: lien.connecte and lien.en_attente == 0)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
        for _ in range(100):
            try:
                await client.get("/healthz")
                break
            except httpx.TransportError:
                await asyncio.sleep(0.02)
        client.headers["Authorization"] = f"Bearer {JETON}"
        yield client, faux_ampli, lien, taches
    for t in taches:
        t.cancel()
    await asyncio.gather(*taches, return_exceptions=True)


class Lecteur:
    """Lit un flux SSE bloc par bloc : un bloc est un événement ou un commentaire."""

    def __init__(self, reponse: httpx.Response):
        self.lignes = reponse.aiter_lines()

    async def bloc(self, delai: float = 2.0) -> list[str]:
        bloc = []
        while True:
            ligne = await asyncio.wait_for(anext(self.lignes), delai)
            if ligne == "":
                if bloc:
                    return bloc
                continue
            bloc.append(ligne)

    async def etat(self, delai: float = 2.0) -> dict:
        """Le prochain événement `state`, battements de cœur sautés."""
        while True:
            bloc = await self.bloc(delai)
            if any(l.startswith("event: state") for l in bloc):
                donnees = [l.removeprefix("data: ") for l in bloc if l.startswith("data: ")]
                return json.loads("\n".join(donnees))


async def test_jeton_exige(flux):
    client, *_ = flux
    r = await client.get("/api/events", headers={"Authorization": "Bearer faux"})
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


async def test_etat_complet_a_la_connexion_comme_api_state(flux):
    client, ampli, *_ = flux
    await ampli.pousser("PWON\rZMON\rMV45\rSIGAME\r")
    await asyncio.sleep(0.05)
    attendu = (await client.get("/api/state")).json()
    async with client.stream("GET", "/api/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        premier = await Lecteur(r).etat()
    assert premier == attendu
    assert premier["power"] is True and premier["zone"] is True and premier["volume"] == -35


async def test_un_evenement_par_changement(flux):
    client, ampli, *_ = flux
    async with client.stream("GET", "/api/events") as r:
        lecteur = Lecteur(r)
        await lecteur.etat()
        await ampli.pousser("PWON\r")
        assert (await lecteur.etat())["power"] is True
        await ampli.pousser("ZMOFF\r")
        e = await lecteur.etat()
        assert e["zone"] is False and e["power"] is True
        await ampli.pousser("PWSTANDBY\r")
        assert (await lecteur.etat())["power"] is False


async def test_une_trame_qui_ne_change_rien_ne_fait_pas_d_evenement(flux):
    client, ampli, *_ = flux
    await ampli.pousser("PWON\r")
    await asyncio.sleep(0.05)
    async with client.stream("GET", "/api/events") as r:
        lecteur = Lecteur(r)
        await lecteur.etat()
        await ampli.pousser("PWON\rPWON\rMUON\r")  # l'ampli répète son état
        e = await lecteur.etat()
        assert e["mute"] is True, "le PWON répété n'a pas fait d'événement"


async def test_coupure_et_reconnexion_du_lien(flux):
    client, ampli, lien, _ = flux
    async with client.stream("GET", "/api/events") as r:
        lecteur = Lecteur(r)
        assert (await lecteur.etat())["connected"] is True
        await ampli.couper()
        assert (await lecteur.etat())["connected"] is False
        assert (await lecteur.etat())["connected"] is True


async def test_battement_de_coeur(flux):
    client, *_ = flux
    async with client.stream("GET", "/api/events") as r:
        lecteur = Lecteur(r)
        await lecteur.etat()
        assert (await lecteur.bloc(BATTEMENT * 5))[0].startswith(":")


async def test_plusieurs_clients_et_depart_d_un_client(flux):
    client, ampli, lien, _ = flux
    async with client.stream("GET", "/api/events") as a:
        la = Lecteur(a)
        await la.etat()
        async with client.stream("GET", "/api/events") as b:
            lb = Lecteur(b)
            await lb.etat()
            await ampli.pousser("PWON\r")
            assert (await la.etat())["power"] is True
            assert (await lb.etat())["power"] is True
        await attendre(lambda: len(lien._abonnes) == 1)  # b parti : désabonné
        await ampli.pousser("PWSTANDBY\r")
        assert (await la.etat())["power"] is False
    await attendre(lambda: not lien._abonnes)


async def test_l_arret_du_lien_ferme_le_flux(flux):
    client, ampli, lien, taches = flux
    async with client.stream("GET", "/api/events") as r:
        lecteur = Lecteur(r)
        await lecteur.etat()
        taches[0].cancel()  # le lien s'arrête (désactivation du plugin)
        assert (await lecteur.etat())["connected"] is False
        with pytest.raises(StopAsyncIteration):
            while True:
                await lecteur.bloc()
    assert not lien._abonnes


async def test_un_client_lent_recoit_le_dernier_etat():
    """Un abonné qui ne lit pas ne fait pas grossir de file : il trouve le
    dernier état à sa prochaine lecture."""
    lien = Lien(lambda: Config("", 23, 0), PILOTES["avrx4000"])
    abonnement = lien.abonner()
    for ligne in ("PWON", "MV45", "PWSTANDBY"):
        lien.pilote.lire(lien.etat, ligne)
        lien._diffuser()
    etat = await abonnement.suivant(0.1)
    assert etat["power"] is False and etat["volume"] == -35
    assert await abonnement.suivant(0.05) is None  # rien de neuf : délai écoulé
    abonnement.retirer()
    assert not lien._abonnes
