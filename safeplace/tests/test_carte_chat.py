"""`safeplace.signaler` (#931) : proposé en carte, tamponné, appliqué, défait."""

import json

import pytest
import pytest_asyncio

from backend.models import Artist, Genre

BASE = "/api/plugins/safeplace/flags"


@pytest_asyncio.fixture
async def artiste(db_session, safeplace, monkeypatch):
    from backend.api import operations as api_operations
    from backend.services import file_ops

    # Le tampon s'applique et se révoque en mode édition ; rien n'écrit /music.
    monkeypatch.setattr(api_operations, "require_edit", lambda: None)
    monkeypatch.setattr(file_ops, "require_edit", lambda: None)
    genre = Genre(name="Rap Worldwide", path="Rap Worldwide")
    db_session.add(genre)
    await db_session.flush()
    a = Artist(folder_name="Bad Guy", genre_id=genre.id, folder_path="Rap Worldwide/Bad Guy")
    db_session.add(a)
    await db_session.commit()
    return a.id


async def _tamponner(client, artist_id, **params):
    """Ce que la carte du chat envoie : une opération par cible, source chat."""
    r = await client.post("/api/operations/staged", json=[{
        "operation_type": "safeplace.signaler", "source": "chat", "target_type": "artist",
        "target_id": artist_id, "params_json": {"reasons": "Condamné en 2024", "severity": "condamné", **params},
    }])
    assert r.status_code in (200, 201), r.text
    return r.json()[0]["id"]


async def _appliquer(client, op_id):
    r = await client.post("/api/operations/apply-staged", json={"operation_ids": [op_id]})
    return next(x for x in r.json()["results"] if x["operation_id"] == op_id)


async def test_propose_au_modele_avec_sa_cible(safeplace):
    from backend.plugins import registres
    from backend.services.chat_service import outils_proposes

    t = registres.operations.proposables_au_chat()["safeplace.signaler"]
    assert t.type_cible == "artist" and "targets = [artist_id]" in t.chat
    propose = next(o for o in outils_proposes() if o["function"]["name"] == "propose_action")
    assert "safeplace.signaler" in propose["function"]["parameters"]["properties"]["type"]["enum"]


async def test_appliquer_confirme_puis_annuler_retire(client, artiste):
    op_id = await _tamponner(client, artiste, source_url="https://exemple.org/a")
    assert (await _appliquer(client, op_id))["status"] == "applied"
    item = (await client.get(f"{BASE}/{artiste}")).json()
    assert (item["pending_review"], item["severity"], item["source_url"]) == (0, "condamné", "https://exemple.org/a")
    assert item["flagged_by"] == "carte"

    r = await client.post(f"/api/operations/staged/{op_id}/revert")
    assert r.status_code == 200, r.text
    assert (await client.get(f"{BASE}/{artiste}")).json() is None


async def test_une_suggestion_en_attente_se_confirme_et_y_retourne(client, artiste):
    await client.post(BASE, json={
        "artist_id": artiste, "reasons": "Source d'origine", "severity": "accusé",
        "flagged_by": "serge", "pending_review": 1,
    })
    op_id = await _tamponner(client, artiste)
    assert (await _appliquer(client, op_id))["status"] == "applied"
    item = (await client.get(f"{BASE}/{artiste}")).json()
    # Confirmée, et ses motifs restent les siens.
    assert (item["pending_review"], item["reasons"], item["severity"]) == (0, "Source d'origine", "accusé")

    assert (await client.post(f"/api/operations/staged/{op_id}/revert")).status_code == 200
    item = (await client.get(f"{BASE}/{artiste}")).json()
    assert (item["pending_review"], item["reasons"], item["flagged_by"]) == (1, "Source d'origine", "serge")


async def test_un_artiste_a_la_corbeille_n_est_pas_signale(client, artiste, db_session):
    from sqlalchemy import text

    op_id = await _tamponner(client, artiste)
    await db_session.execute(text("UPDATE artists SET trashed = 1 WHERE id = :id"), {"id": artiste})
    await db_session.commit()
    assert (await _appliquer(client, op_id))["status"] != "applied"
    assert (await client.get(f"{BASE}/{artiste}")).json() is None


async def test_deja_signale_est_range_sans_effet(client, artiste):
    await client.post(BASE, json={"artist_id": artiste, "severity": "condamné"})
    op_id = await _tamponner(client, artiste, severity="autre")
    resultat = await _appliquer(client, op_id)
    assert resultat["status"] != "applied"
    # Le signalement acté n'a pas été réécrit par la carte.
    assert (await client.get(f"{BASE}/{artiste}")).json()["severity"] == "condamné"


async def test_gravite_inventee_echoue_avec_son_motif(client, artiste):
    op_id = await _tamponner(client, artiste, severity="pire")
    resultat = await _appliquer(client, op_id)
    assert resultat["status"] == "failed" and "gravité" in json.dumps(resultat, ensure_ascii=False)
