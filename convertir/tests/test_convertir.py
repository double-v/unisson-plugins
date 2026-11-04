"""La conversion WMA → MP3, de l'aperçu à la révocation (#950).

Les fichiers sont de **vrais** WMA (ffmpeg, wmav2) tagués en ASF par mutagen :
le geste est testé en aller-retour sur le disque — encoder, relire les tags,
vérifier que l'original est à la corbeille, révoquer, comparer à l'octet
près (règle #843).
"""

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.models import Album, Artist, Genre, ScanRun, StagedOperation, Track

ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")

pytestmark = pytest.mark.asyncio

DOSSIER = "Albums others/Anonyme/Concert"
APERCU = "/api/plugins/convertir/albums/{}/apercu"
MBID_ALBUM = "0f9f2a7e-3c1b-4a5e-9d6e-1b2c3d4e5f60"
MBID_PISTE = "a1b2c3d4-e5f6-4789-8abc-def012345678"
IMAGE = b"\xff\xd8\xff\xe0" + b"jpeg" * 200


@pytest_asyncio.fixture
async def album(db_session, convertir, disque, wma):
    """Un album de deux WMA tagués et d'une pochette, en base et sur disque."""
    scan = ScanRun(status="completed", started_at=datetime.now(timezone.utc).isoformat())
    genre = Genre(name="Albums others", path="Albums others")
    db_session.add_all([scan, genre])
    await db_session.flush()
    artiste = Artist(folder_name="Anonyme", name_from_nfo="Anonyme", genre_id=genre.id, folder_path="Albums others/Anonyme")
    db_session.add(artiste)
    await db_session.flush()
    a = Album(artist_id=artiste.id, genre_id=genre.id, folder_name="Concert", folder_path=DOSSIER,
              name_from_folder="Concert", scan_run_id=scan.id)
    db_session.add(a)
    await db_session.flush()
    pistes = []
    for n, debit in ((1, 160), (2, 192)):
        nom = f"Piste {n}.wma"
        wma(disque / DOSSIER / nom, debit=debit, tags={
            "Title": f"Titre {n}", "Author": "Anonyme", "WM/AlbumTitle": "Concert",
            "WM/TrackNumber": str(n), "WM/Year": "2001", "MusicBrainz/Album Id": MBID_ALBUM,
            "MusicBrainz/Track Id": MBID_PISTE,
        }, image=IMAGE if n == 1 else None)
        t = Track(album_id=a.id, filename=nom, relative_path=f"{DOSSIER}/{nom}", format="WMA",
                  bitrate_kbps=debit, duration_seconds=2.0, track_number=n)
        db_session.add(t)
        pistes.append(t)
    (disque / DOSSIER / "cover.jpg").write_bytes(b"pochette")
    await db_session.commit()
    return {"id": a.id, "pistes": [t.id for t in pistes]}


def _empreinte(racine: Path) -> dict[str, str]:
    return {
        str(p.relative_to(racine)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(racine.rglob("*"))
        if p.is_file() and not str(p.relative_to(racine)).startswith("trashed/")
    }


async def _tamponner(client, album_id: int, track_ids: list[int]) -> int:
    r = await client.post("/api/operations/staged", json=[{
        "operation_type": "convertir.mp3", "source": "convertir", "target_type": "album",
        "target_id": album_id, "params_json": {"track_ids": track_ids},
    }])
    assert r.status_code == 200, r.text
    (op,) = r.json()
    assert op["status"] == "pending"  # jamais d'envoi automatique : un encodage s'approuve
    return op["id"]


# ── La décision, sans disque ─────────────────────────────────────────────


async def test_le_debit_cible_ne_descend_jamais_et_ne_gonfle_pas(convertir):
    from unisson_plugins.convertir.conversion import palier

    assert [palier(d) for d in (128, 130, 192, 193, 320, 448)] == [128, 160, 192, 224, 320, 320]
    assert palier(None) == 192


async def test_le_wma_lossless_n_est_jamais_converti_en_mp3(convertir):
    from unisson_plugins.convertir.conversion import decider

    piste = decider({"id": 1, "relative_path": "a/b.wma", "format": "WMA", "bitrate_kbps": 900},
                    {"codec": "wmalossless", "debit": 900, "duree": 1.0}, lambda _: False)

    assert not piste.convertible and piste.motif == "sans_perte"


# ── L'aperçu ─────────────────────────────────────────────────────────────


@ffmpeg
async def test_apercu_annonce_pistes_debits_et_corbeille(client, album, disque):
    avant = _empreinte(disque)

    r = await client.get(APERCU.format(album["id"]))

    assert r.status_code == 200, r.text
    vue = r.json()
    assert vue["a_convertir"] == 2 and vue["mode_edition"] is True
    assert [(p["nom_cible"], p["debit_source"], p["debit_cible"]) for p in vue["pistes"]] == [
        ("Piste 1.mp3", 160, 160), ("Piste 2.mp3", 192, 192),
    ]
    assert vue["corbeille"] == [f"{DOSSIER}/Piste 1.wma", f"{DOSSIER}/Piste 2.wma"]
    assert _empreinte(disque) == avant  # l'aperçu n'écrit rien


@ffmpeg
async def test_apercu_ecarte_un_fichier_illisible_et_une_place_prise(client, album, disque):
    (disque / DOSSIER / "Piste 1.wma").write_bytes(b"pas du wma")
    (disque / DOSSIER / "Piste 2.mp3").write_bytes(b"deja la")

    vue = (await client.get(APERCU.format(album["id"]))).json()

    assert [p["motif"] for p in vue["pistes"]] == ["illisible", "place_prise"]
    assert vue["a_convertir"] == 0 and vue["corbeille"] == []


async def test_apercu_d_un_album_inconnu_rend_404(client, convertir):
    assert (await client.get(APERCU.format(999_999))).status_code == 404


# ── Appliquer, relire, révoquer ──────────────────────────────────────────


@ffmpeg
async def test_conversion_pose_des_mp3_tagues_et_met_les_wma_a_la_corbeille(client, db_session, album, disque):
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3

    from backend.services.file_ops import apply_staged_batch

    op_id = await _tamponner(client, album["id"], album["pistes"])

    resultat = await apply_staged_batch([op_id])

    assert (resultat["applied"], resultat["errors"]) == (1, []), resultat
    assert sorted(p.name for p in (disque / DOSSIER).iterdir()) == ["Piste 1.mp3", "Piste 2.mp3", "cover.jpg"]
    assert (disque / "trashed" / DOSSIER / "Piste 1.wma").is_file()
    mp3 = disque / DOSSIER / "Piste 1.mp3"
    assert round(MP3(str(mp3)).info.bitrate / 1000) == 160
    assert abs(MP3(str(mp3)).info.length - 2.0) < 1.0
    tags = ID3(str(mp3))
    assert tags.version[:2] == (2, 4)
    assert str(tags["TIT2"]) == "Titre 1" and str(tags["TPE1"]) == "Anonyme" and str(tags["TALB"]) == "Concert"
    assert str(tags["TRCK"]) == "1" and str(tags["TDRC"]) == "2001"
    assert str(tags["TXXX:MusicBrainz Album Id"]) == MBID_ALBUM
    assert tags["UFID:http://musicbrainz.org"].data == MBID_PISTE.encode()
    assert tags.getall("APIC")[0].data == IMAGE
    op = await db_session.get(StagedOperation, op_id)
    await db_session.refresh(op)
    assert op.status == "applied"
    assert op.get_params()["revert_data"]["poses"] == [f"{DOSSIER}/Piste 1.mp3", f"{DOSSIER}/Piste 2.mp3"]


@ffmpeg
async def test_revocation_rend_les_wma_a_l_octet_pres(client, db_session, album, disque):
    from backend.services.file_ops import apply_staged_batch, revert_staged_operation

    avant = _empreinte(disque)
    op_id = await _tamponner(client, album["id"], album["pistes"])
    await apply_staged_batch([op_id])

    await revert_staged_operation(op_id)

    assert _empreinte(disque) == avant
    assert (disque / "trashed" / DOSSIER / "Piste 1.mp3").is_file()  # retiré, jamais effacé
    db_session.expire_all()
    pistes = (await db_session.execute(select(Track).where(Track.album_id == album["id"]))).scalars().all()
    assert sorted(t.id for t in pistes) == album["pistes"]


@ffmpeg
async def test_un_album_change_depuis_l_apercu_n_est_pas_converti(client, db_session, album, disque):
    from backend.services.file_ops import apply_staged_batch

    op_id = await _tamponner(client, album["id"], album["pistes"])
    (disque / DOSSIER / "Piste 2.mp3").write_bytes(b"pose a la main")
    avant = _empreinte(disque)

    resultat = await apply_staged_batch([op_id])

    assert resultat["applied"] == 0
    assert _empreinte(disque) == avant
    op = await db_session.get(StagedOperation, op_id)
    await db_session.refresh(op)
    assert op.status in ("failed", "obsolete") and op.reason == "perime"


@ffmpeg
async def test_sans_mode_edition_rien_n_est_encode_ni_deplace(client, db_session, album, disque, monkeypatch):
    from backend.config import settings
    from backend.services.file_ops import apply_staged_batch

    op_id = await _tamponner(client, album["id"], album["pistes"])
    monkeypatch.setattr(settings, "edit_mode", False)
    avant = _empreinte(disque)

    await apply_staged_batch([op_id])

    assert _empreinte(disque) == avant


# ── Le juge du tampon ────────────────────────────────────────────────────


@ffmpeg
async def test_le_juge_range_une_conversion_deja_faite(client, db_session, album, disque):
    from unisson_plugins.convertir.service import verifier

    op_id = await _tamponner(client, album["id"], album["pistes"])
    op = await db_session.get(StagedOperation, op_id)
    assert (await verifier(op, "legere", None)).sorte == "applicable"
    assert (await verifier(op, "complete", None)).sorte == "applicable"
    for t in (await db_session.execute(select(Track).where(Track.album_id == album["id"]))).scalars():
        t.format = "MP3"
    await db_session.commit()

    verdict = await verifier(op, "legere", None)

    assert (verdict.sorte, verdict.reason) == ("effet_present", "deja_converti")
