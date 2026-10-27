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
    assert {"safeplace_check_artist_status", "safeplace_suggest_addition"} <= noms


async def test_verifier_exact_flou_et_absent(client, artistes):
    await client.post(BASE, json={"artist_id": artistes["signale"], "reasons": "Motif", "severity": "condamné"})
    verifier = await _outil("safeplace_check_artist_status")
    exact = await verifier({"artist_name": "Bad Guy"})
    assert exact["in_safeplace"] is True and exact["severity"] == "condamné" and exact["reasons"] == "Motif"
    assert (await verifier({"artist_name": "Bad Gu"}))["in_safeplace"] is True
    assert await verifier({"artist_name": "Nice Person"}) == {"in_safeplace": False}
    assert "error" in await verifier({"artist_name": "  "})


async def test_verifier_sans_aucun_signalement(artistes):
    verifier = await _outil("safeplace_check_artist_status")
    assert await verifier({"artist_name": "Bad Guy"}) == {"in_safeplace": False}


async def test_suggerer_pose_un_signalement_en_attente(client, artistes):
    suggerer = await _outil("safeplace_suggest_addition")
    r = await suggerer({"artist_name": "Nice Persn", "reasons": "Source X", "severity": "accusé"})
    assert r["status"] == "suggested" and r["artist_id"] == artistes["autre"]
    item = (await client.get(f"{BASE}/{artistes['autre']}")).json()
    assert (item["pending_review"], item["flagged_by"], item["severity"]) == (1, "serge", "accusé")


async def test_suggerer_ne_retrograde_pas_un_signalement_acte(client, artistes):
    await client.post(BASE, json={"artist_id": artistes["signale"], "severity": "condamné"})
    suggerer = await _outil("safeplace_suggest_addition")
    r = await suggerer({"artist_name": "Bad Guy", "reasons": "autre chose", "severity": "autre"})
    assert r["status"] == "already_flagged"
    item = (await client.get(f"{BASE}/{artistes['signale']}")).json()
    assert (item["pending_review"], item["severity"]) == (0, "condamné")


async def test_suggerer_artiste_inconnu_ou_gravite_inventee(artistes):
    suggerer = await _outil("safeplace_suggest_addition")
    assert "introuvable" in (await suggerer({"artist_name": "Zzzz Qqqq", "reasons": "x", "severity": "autre"}))["error"]
    assert "gravité" in (await suggerer({"artist_name": "Bad Guy", "reasons": "x", "severity": "pire"}))["error"]
