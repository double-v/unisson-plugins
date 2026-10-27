"""Les outils de l'assistant, par le registre du cœur (portés de #81)."""

import pytest_asyncio

from backend.models import Artist, Genre

BASE = "/api/plugins/safeplace/flags"


async def _outil(nom):
    from backend.plugins import registres

    return registres.outils_chat.valeurs()[nom][1]


@pytest_asyncio.fixture
async def artistes(db_session, safeplace):
    genre = Genre(name="Rap Worldwide", path="Rap Worldwide")
    db_session.add(genre)
    await db_session.flush()
    signale = Artist(folder_name="Bad Guy", genre_id=genre.id, folder_path="Rap Worldwide/Bad Guy")
    autre = Artist(folder_name="Nice Person", genre_id=genre.id, folder_path="Rap Worldwide/Nice Person")
    db_session.add_all([signale, autre])
    await db_session.commit()
    return {"signale": signale.id, "autre": autre.id}


async def test_outils_proposes_au_modele(safeplace):
    from backend.services.chat_service import outils_proposes

    noms = {o["function"]["name"] for o in outils_proposes()}
    assert "safeplace_check_artist_status" in noms
    # Signaler passe par une carte (#931), plus par un outil qui écrit.
    assert "safeplace_suggest_addition" not in noms


async def test_verifier_exact_flou_et_absent(client, artistes):
    await client.post(BASE, json={"artist_id": artistes["signale"], "reasons": "Motif", "severity": "condamné"})
    verifier = await _outil("safeplace_check_artist_status")
    exact = await verifier({"artist_name": "Bad Guy"})
    assert exact["in_safeplace"] is True and exact["severity"] == "condamné" and exact["reasons"] == "Motif"
    assert (await verifier({"artist_name": "Bad Gu"}))["in_safeplace"] is True
    # Absent de la safeplace mais dans la bibliothèque : son id, cible d'une carte.
    assert await verifier({"artist_name": "Nice Person"}) == {
        "in_safeplace": False, "artist_id": artistes["autre"], "artist_name": "Nice Person",
    }
    assert await verifier({"artist_name": "Zzzz Qqqq"}) == {"in_safeplace": False}
    assert "error" in await verifier({"artist_name": "  "})


async def test_verifier_sans_aucun_signalement(artistes):
    verifier = await _outil("safeplace_check_artist_status")
    assert (await verifier({"artist_name": "Bad Guy"}))["in_safeplace"] is False
