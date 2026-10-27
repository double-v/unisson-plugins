"""Les signalements, par les routes du plugin (portés du cœur, #72)."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from backend.models import Album, Artist, Genre, ScanRun, Track

BASE = "/api/plugins/safeplace/flags"


@pytest_asyncio.fixture
async def bibliotheque(db_session, safeplace):
    """Deux artistes du même genre : le premier a deux albums (15 Mo), le
    second un seul (2 Mo)."""
    scan = ScanRun(status="completed", started_at=datetime.now(timezone.utc).isoformat())
    genre = Genre(name="Rap Francophone", path="Rap Francophone")
    db_session.add_all([scan, genre])
    await db_session.flush()
    a = Artist(folder_name="Bad Guy", name_from_nfo="Bad Guy", genre_id=genre.id, folder_path="Rap Francophone/Bad Guy")
    b = Artist(folder_name="Other Guy", name_from_nfo="Other Guy", genre_id=genre.id, folder_path="Rap Francophone/Other Guy")
    db_session.add_all([a, b])
    await db_session.flush()

    def album(artiste, i, trashed=0):
        return Album(artist_id=artiste.id, genre_id=genre.id, folder_name=f"Album {i}",
                     folder_path=f"Rap Francophone/{artiste.folder_name}/Album {i}",
                     name_from_folder=f"Album {i}", scan_run_id=scan.id, trashed=trashed)

    a1, a2, b1 = album(a, 1), album(a, 2), album(b, 1)
    a3 = album(a, 3, trashed=1)
    db_session.add_all([a1, a2, b1, a3])
    await db_session.flush()
    db_session.add_all([
        Track(album_id=a1.id, filename="01.flac", relative_path="x/01.flac", format="FLAC", file_size_bytes=10_000_000),
        Track(album_id=a2.id, filename="01.flac", relative_path="x/01.flac", format="FLAC", file_size_bytes=5_000_000),
        Track(album_id=b1.id, filename="01.mp3", relative_path="x/01.mp3", format="MP3", file_size_bytes=2_000_000),
        Track(album_id=a3.id, filename="01.flac", relative_path="x/01.flac", format="FLAC", file_size_bytes=99_000_000),
    ])
    await db_session.commit()
    return {"genre": genre.id, "a": a.id, "b": b.id}


async def test_poser_un_signalement_enrichi(client, bibliotheque):
    r = await client.post(BASE, json={"artist_id": bibliotheque["a"], "reasons": "Motif", "severity": "condamné",
                                      "source_url": "https://exemple.org"})
    assert r.status_code == 201
    item = r.json()
    assert item["artist_name"] == "Bad Guy"
    assert item["genre_name"] == "Rap Francophone"
    # La corbeille ne compte pas.
    assert (item["album_count"], item["total_size_bytes"]) == (2, 15_000_000)
    assert (item["severity"], item["flagged_by"], item["pending_review"]) == ("condamné", "user", 0)


async def test_reposer_met_a_jour(client, bibliotheque):
    await client.post(BASE, json={"artist_id": bibliotheque["a"], "reasons": "v1"})
    r = await client.post(BASE, json={"artist_id": bibliotheque["a"], "reasons": "v2", "severity": "accusé"})
    assert (r.json()["reasons"], r.json()["severity"]) == ("v2", "accusé")
    assert (await client.get(BASE)).json()["total"] == 1


async def test_artiste_inconnu_404(client, bibliotheque):
    assert (await client.post(BASE, json={"artist_id": 999_999})).status_code == 404


async def test_liste_pageout_et_filtres(client, bibliotheque):
    await client.post(BASE, json={"artist_id": bibliotheque["a"], "severity": "condamné"})
    await client.post(BASE, json={"artist_id": bibliotheque["b"], "severity": "accusé", "pending_review": 1})
    page = (await client.get(BASE)).json()
    assert set(page) == {"items", "total", "offset", "limit"}
    assert (page["total"], page["limit"]) == (2, 100)
    assert [i["artist_id"] for i in (await client.get(BASE, params={"severity": "condamné"})).json()["items"]] == [bibliotheque["a"]]
    assert (await client.get(BASE, params={"genre_id": bibliotheque["genre"]})).json()["total"] == 2
    assert (await client.get(BASE, params={"genre_id": 999_999})).json()["total"] == 0
    assert [i["artist_id"] for i in (await client.get(BASE, params={"pending_review": 1})).json()["items"]] == [bibliotheque["b"]]


async def test_filtre_inconnu_422(client, bibliotheque):
    assert (await client.get(BASE, params={"severity": "inventée"})).status_code == 422
    assert (await client.get(BASE, params={"pending_review": 7})).status_code == 422


async def test_confirmer_puis_retirer(client, bibliotheque):
    a = bibliotheque["a"]
    await client.post(BASE, json={"artist_id": a, "pending_review": 1, "flagged_by": "serge"})
    r = await client.put(f"{BASE}/{a}/confirm")
    assert r.status_code == 200 and r.json()["pending_review"] == 0
    assert (await client.put(f"{BASE}/{bibliotheque['b']}/confirm")).status_code == 404
    assert (await client.delete(f"{BASE}/{a}")).status_code == 200
    assert (await client.delete(f"{BASE}/{a}")).status_code == 404
    assert (await client.get(f"{BASE}/{a}")).json() is None


async def test_la_fiche_artiste_du_coeur_ne_porte_plus_le_signalement(client, bibliotheque):
    """Le badge et le bloc sont des contributions du plugin : la sortie
    artiste du cœur ne gagne aucun champ."""
    await client.post(BASE, json={"artist_id": bibliotheque["a"]})
    fiche = (await client.get(f"/api/artists/{bibliotheque['a']}")).json()
    assert "is_flagged" not in fiche and "flag_summary" not in fiche


async def test_desactive_404_et_donnees_gardees(client, bibliotheque):
    from backend.plugins import chargeur

    await client.post(BASE, json={"artist_id": bibliotheque["a"]})
    await chargeur.desactiver("safeplace")
    assert (await client.get(BASE)).status_code == 404
    await chargeur.activer("safeplace")
    assert (await client.get(BASE)).json()["total"] == 1


async def test_supprimer_l_artiste_emporte_son_signalement(client, bibliotheque, db_session):
    from sqlalchemy import text

    await client.post(BASE, json={"artist_id": bibliotheque["b"]})
    await db_session.execute(text("DELETE FROM tracks WHERE album_id IN (SELECT id FROM albums WHERE artist_id = :a)"), {"a": bibliotheque["b"]})
    await db_session.execute(text("DELETE FROM albums WHERE artist_id = :a"), {"a": bibliotheque["b"]})
    await db_session.execute(text("DELETE FROM artists WHERE id = :a"), {"a": bibliotheque["b"]})
    await db_session.commit()
    assert (await client.get(BASE)).json()["total"] == 0
