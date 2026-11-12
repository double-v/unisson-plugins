"""La conversion WMA → MP3, de l'aperçu à la révocation (#950).

Les fichiers sont de **vrais** WMA (ffmpeg, wmav2) tagués en ASF par mutagen :
le geste est testé en aller-retour sur le disque — encoder, relire les tags,
vérifier que l'original est à la corbeille, révoquer, comparer à l'octet
près (règle #843).
"""

import asyncio
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.models import Album, Artist, Library, ScanRun, StagedOperation, Track

ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")

pytestmark = pytest.mark.asyncio

DOSSIER = "Albums others/Anonyme/Concert"
APERCU = "/api/plugins/convertir/albums/{}/apercu"
MBID_ALBUM = "0f9f2a7e-3c1b-4a5e-9d6e-1b2c3d4e5f60"
MBID_PISTE = "a1b2c3d4-e5f6-4789-8abc-def012345678"
IMAGE = b"\xff\xd8\xff\xe0" + b"jpeg" * 200


async def _creer_album(db_session, wma, *, bibliotheque: str, chemin_bib: str, dossier: str, disque: Path) -> dict:
    """Deux WMA tagués et une pochette, en base (`dossier`, chemin logique) et
    sur le disque (`disque`, là où vit vraiment la bibliothèque)."""
    scan = ScanRun(status="completed", started_at=datetime.now(timezone.utc).isoformat())
    bib = Library(name=bibliotheque, path=chemin_bib)
    db_session.add_all([scan, bib])
    await db_session.flush()
    artiste = Artist(folder_name="Anonyme", name_from_nfo="Anonyme", library_id=bib.id,
                     folder_path=f"{bibliotheque}/Anonyme")
    db_session.add(artiste)
    await db_session.flush()
    a = Album(artist_id=artiste.id, library_id=bib.id, folder_name="Concert", folder_path=dossier,
              name_from_folder="Concert", scan_run_id=scan.id)
    db_session.add(a)
    await db_session.flush()
    pistes = []
    for n, debit in ((1, 160), (2, 192)):
        nom = f"Piste {n}.wma"
        wma(disque / nom, debit=debit, tags={
            "Title": f"Titre {n}", "Author": "Anonyme", "WM/AlbumTitle": "Concert",
            "WM/TrackNumber": str(n), "WM/Year": "2001", "MusicBrainz/Album Id": MBID_ALBUM,
            "MusicBrainz/Track Id": MBID_PISTE,
        }, image=IMAGE if n == 1 else None)
        t = Track(album_id=a.id, filename=nom, relative_path=f"{dossier}/{nom}", format="WMA",
                  bitrate_kbps=debit, duration_seconds=2.0, track_number=n)
        db_session.add(t)
        pistes.append(t)
    (disque / "cover.jpg").write_bytes(b"pochette")
    await db_session.commit()
    return {"id": a.id, "pistes": [t.id for t in pistes]}


@pytest_asyncio.fixture
async def album(db_session, convertir, disque, wma):
    """Un album de deux WMA tagués et d'une pochette, en base et sur disque."""
    return await _creer_album(db_session, wma, bibliotheque="Albums others", chemin_bib="Albums others",
                              dossier=DOSSIER, disque=disque / DOSSIER)


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
    # Les lignes sont gardées et pointent sur les MP3 : rien de ce qui les vise ne part.
    db_session.expire_all()
    pistes = (await db_session.execute(select(Track).where(Track.album_id == album["id"]).order_by(Track.id))).scalars().all()
    assert [(t.id, t.format) for t in pistes] == [(album["pistes"][0], "MP3"), (album["pistes"][1], "MP3")]


@ffmpeg
async def test_le_scanner_du_coeur_relit_le_mp3_pose(client, album, disque):
    """Ce que la conversion promet (« redevient taguable ») se juge par le
    vrai lecteur du cœur, pas par mutagen seul."""
    from backend.services.file_ops import apply_staged_batch
    from backend.services.metadata import read_track_metadata

    await apply_staged_batch([await _tamponner(client, album["id"], album["pistes"])])

    meta = read_track_metadata(disque / DOSSIER / "Piste 1.mp3", disque)
    assert (meta.format, meta.title_tag, meta.artist_tag, meta.album_tag) == ("MP3", "Titre 1", "Anonyme", "Concert")
    assert (meta.track_number, meta.release_date, meta.musicbrainz_track_id) == (1, "2001", MBID_PISTE)


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
    # Une autre conversion des mêmes pistes est passée entre-temps.
    autre = await _tamponner_sans_dedup(db_session, album)
    from backend.services.file_ops import apply_staged_batch
    await apply_staged_batch([autre])

    verdict = await verifier(op, "legere", None)

    assert (verdict.sorte, verdict.reason) == ("effet_present", "deja_converti")


@ffmpeg
async def test_le_juge_ne_range_pas_ce_qu_il_n_a_pas_su_lire(client, db_session, album, disque, monkeypatch):
    """Un ffprobe qui échoue (NAS lent, délai) rend `indecidable`, jamais
    `obsolete` : la conversion reste à décider (V9)."""
    from unisson_plugins.convertir import conversion
    from unisson_plugins.convertir.service import verifier

    op_id = await _tamponner(client, album["id"], album["pistes"])
    op = await db_session.get(StagedOperation, op_id)

    async def rate(_):
        return None

    monkeypatch.setattr(conversion, "sonder", rate)

    assert (await verifier(op, "complete", None)).sorte == "indecidable"


async def test_le_juge_dit_disparu_ce_qui_n_a_pas_ete_converti(client, db_session, album, disque):
    """Des WMA retirés par un autre geste ne font pas une conversion faite (V9)."""
    from unisson_plugins.convertir.service import verifier

    op_id = await _tamponner(client, album["id"], album["pistes"])
    op = await db_session.get(StagedOperation, op_id)
    for t in (await db_session.execute(select(Track).where(Track.album_id == album["id"]))).scalars():
        await db_session.delete(t)
    await db_session.commit()

    verdict = await verifier(op, "legere", None)

    assert (verdict.sorte, verdict.reason) == ("sans_objet", "pistes_disparues")


async def _tamponner_sans_dedup(db_session, album) -> int:
    op = StagedOperation(operation_type="convertir.mp3", source="convertir", status="pending",
                         target_type="album", target_id=album["id"],
                         created_at=datetime.now(timezone.utc).isoformat())
    op.set_params({"track_ids": album["pistes"]})
    db_session.add(op)
    await db_session.commit()
    return op.id


# ── Les rips réels : tags sales, images tordues, sources abîmées ─────────


@ffmpeg
async def test_une_image_mal_formee_ne_fige_rien_et_est_annoncee(client, db_session, convertir, disque, wma):
    """Un `WM/Picture` sans terminateur faisait boucler la lecture à l'infini
    dans la boucle d'événements (V4)."""
    from mutagen.asf import ASF, ASFByteArrayAttribute

    from unisson_plugins.convertir.conversion import lire_image_asf, tags_id3

    f = wma(disque / "x.wma", tags={"Title": "x"})
    tordue = bytes([3]) + (100).to_bytes(4, "little") + "image/jpeg".encode("utf-16-le")  # pas de nul
    a = ASF(str(f))
    a["WM/Picture"] = [ASFByteArrayAttribute(tordue)]
    a.save()

    assert lire_image_asf(tordue) is None
    cadres, ecartes = await asyncio.wait_for(asyncio.to_thread(tags_id3, f), 5)
    assert ecartes == ["WM/Picture illisible"] and not [c for c in cadres if c.FrameID == "APIC"]


@ffmpeg
async def test_annee_et_genre_sales_ne_font_pas_echouer_l_album(convertir, disque, wma, tmp_path):
    """Une année « Unknown » ou un genre ID3v1 numérique faisaient refuser le
    contrôle de tout l'album ; « 04/05/2001 » était réécrit en silence (V11)."""
    from mutagen.id3 import ID3

    from unisson_plugins.convertir.conversion import convertir as encoder, ecartes_de

    for annee, genre, attendu in (("Unknown", "13", ("", "Pop")), ("04/05/2001", "(12)Other", ("", "Other")),
                                  ("2001-05-04T00:00:00Z", "Rap", ("2001-05-04", "Rap"))):
        src = wma(tmp_path / f"{genre}.wma", tags={"Title": "t", "WM/Year": annee, "WM/Genre": genre})
        out = tmp_path / f"{genre}.mp3"

        ecartes = await encoder(src, out, 192, None)

        tags = ID3(str(out))
        assert (str(tags["TDRC"]) if "TDRC" in tags else "", str(tags["TCON"])) == attendu
        assert ecartes == ecartes_de(src) == ([] if attendu[0] else [f"WM/Year « {annee} »"])


@ffmpeg
async def test_une_source_abimee_n_est_pas_posee(convertir, wma, tmp_path):
    """Un WMA dont une partie est illisible : ffmpeg rend 0 et saute le trou
    en silence ; le contrôle de durée doit le voir (V18)."""
    from unisson_plugins.convertir.conversion import EchecConversion, convertir as encoder, sonder

    src = wma(tmp_path / "s.wma", duree=30.0)
    duree = (await sonder(src))["duree"]
    octets = bytearray(src.read_bytes())
    milieu, n = len(octets) // 2, len(octets) // 50
    for i in range(milieu, milieu + n):
        octets[i] = (i * 7919) & 0xFF
    src.write_bytes(bytes(octets))

    with pytest.raises(EchecConversion) as e:
        await encoder(src, tmp_path / "s.mp3", 192, duree)
    assert e.value.motif == "controle"


async def test_un_sous_processus_qui_pend_est_tue(convertir):
    """Sans délai, un ffmpeg bloqué laissait l'opération sans état terminal (V12)."""
    from unisson_plugins.convertir.conversion import EchecConversion, _executer

    with pytest.raises(EchecConversion) as e:
        await _executer("sleep", "30", delai=0.3)
    assert e.value.motif == "delai"


async def test_un_nom_que_le_coeur_refuserait_est_ecarte_a_l_apercu(convertir):
    """Un nom refusé par le cœur ne doit pas coûter l'encodage (V13)."""
    from unisson_plugins.convertir.conversion import decider, nom_cible

    assert nom_cible("a/ .Intro .wma") == "Intro.mp3"
    piste = decider({"id": 1, "relative_path": "a/....wma", "format": "WMA", "bitrate_kbps": 128},
                    {"codec": "wmav2", "debit": 128, "duree": 1.0}, lambda _: False)
    assert not piste.convertible and piste.motif == "nom_invalide"


@ffmpeg
async def test_pendant_un_scan_rien_n_est_encode(client, db_session, album, disque, monkeypatch):
    """Le cœur refuse de poser pendant un scan : le plugin refuse avant
    d'encoder (V14)."""
    from backend.services.file_ops import apply_staged_batch
    from unisson_plugins.convertir import conversion

    op_id = await _tamponner(client, album["id"], album["pistes"])
    db_session.add(ScanRun(status="running", started_at=datetime.now(timezone.utc).isoformat()))
    await db_session.commit()
    encodages = []

    async def compter(*a, **k):
        encodages.append(a)

    monkeypatch.setattr(conversion, "convertir", compter)

    await apply_staged_batch([op_id])

    assert encodages == []


# ── Une bibliothèque sur un autre volume (spec 025 US3) ──────────────────


@ffmpeg
async def test_un_album_d_une_bibliotheque_sur_un_autre_volume_se_convertit_et_se_revoque(
        client, db_session, convertir, disque, wma, tmp_path, monkeypatch):
    """La bibliothèque `Vinyles` vit hors de la racine (un second dossier,
    comme un autre volume) : `racine / relative_path` n'y mène pas. L'aperçu
    lit les WMA là où ils sont, les MP3 sont posés à côté d'eux, et la
    révocation rend l'album à l'octet près ; rien n'apparaît sous la racine."""
    from mutagen.mp3 import MP3

    from backend.config import settings
    from backend.services.file_ops import apply_staged_batch, revert_staged_operation

    vinyles = tmp_path / "disque2" / "Vinyles"
    vinyles.mkdir(parents=True)
    monkeypatch.setattr(settings, "library_folders", f"Albums others|{vinyles}")
    dossier = "Vinyles/Anonyme/Concert"
    ici = vinyles / "Anonyme" / "Concert"
    album = await _creer_album(db_session, wma, bibliotheque="Vinyles", chemin_bib=str(vinyles),
                               dossier=dossier, disque=ici)
    avant = _empreinte(vinyles)

    vue = (await client.get(APERCU.format(album["id"]))).json()

    assert [(p["motif"], p["nom_cible"]) for p in vue["pistes"]] == [(None, "Piste 1.mp3"), (None, "Piste 2.mp3")]
    assert vue["a_convertir"] == 2 and vue["corbeille"] == [f"{dossier}/Piste 1.wma", f"{dossier}/Piste 2.wma"]

    op_id = await _tamponner(client, album["id"], album["pistes"])
    resultat = await apply_staged_batch([op_id])

    assert (resultat["applied"], resultat["errors"]) == (1, []), resultat
    assert sorted(p.name for p in ici.iterdir()) == ["Piste 1.mp3", "Piste 2.mp3", "cover.jpg"]
    assert round(MP3(str(ici / "Piste 1.mp3")).info.bitrate / 1000) == 160
    assert (disque / "trashed" / dossier / "Piste 1.wma").is_file()
    assert not (disque / "Vinyles").exists()  # rien posé sous la racine

    await revert_staged_operation(op_id)

    assert _empreinte(vinyles) == avant
