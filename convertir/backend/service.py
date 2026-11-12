"""L'aperçu d'un album et le type d'opération `convertir.mp3` (#950).

Le plan est **recalculé** à l'application, sur le disque courant, et doit
porter les mêmes pistes que celui qu'on a tamponné : un album rescanné,
retagué ou déjà converti entre-temps n'est jamais converti à l'aveugle.

Un chemin stocké en base se lit par `ctx.chemin_disque` : une bibliothèque
peut vivre sur un autre volume (spec 025 US3), où `racine / relative_path`
ne mène pas. Rien n'est déplacé ici : les MP3 sont préparés dans un dossier
temporaire, puis `ctx.remplacer_pistes` les pose à côté des WMA (sur leur
volume), met les WMA à la corbeille et fait pointer chaque ligne de piste
sur son MP3 (favoris, playlists et écoutes restent), tout ou rien. La
révocation est `ctx.retablir_pistes`.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import bindparam, text

from unisson.plugin import RefusRemplacement, Verdict

from . import conversion

_ctx: dict = {}

FORMATS = ("WMA",)
MOTIFS = {
    "sans_perte": "WMA Lossless : le convertir en MP3 jetterait une copie sans perte",
    "codec_inconnu": "codec que la conversion ne connaît pas",
    "illisible": "ffprobe ne lit pas ce fichier",
    "ffmpeg_absent": "ffmpeg est introuvable sur le serveur",
    "nom_invalide": "le nom du fichier ne donne pas de nom MP3 valable",
    "place_prise": "un fichier du même nom en .mp3 est déjà dans le dossier",
}


def ctx():
    return _ctx["ctx"]


async def _album(session, album_id: int) -> dict | None:
    ligne = (await session.execute(
        text("SELECT id, folder_path, trashed FROM albums WHERE id = :a"), {"a": album_id}
    )).first()
    return dict(ligne._mapping) if ligne else None


async def _pistes(session, album_id: int) -> list[dict]:
    lignes = await session.execute(
        text(
            "SELECT id, relative_path, format, bitrate_kbps, duration_seconds FROM tracks "
            "WHERE album_id = :a AND upper(format) IN :f "
            "ORDER BY disc_number NULLS FIRST, track_number NULLS LAST, filename"
        ).bindparams(bindparam("f", expanding=True)),
        {"a": album_id, "f": list(FORMATS)},
    )
    return [dict(l._mapping) for l in lignes]


async def _lignes(session, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    lignes = await session.execute(
        text("SELECT id, album_id, format FROM tracks WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    return {l.id: dict(l._mapping) for l in lignes}


async def scan_en_cours(session) -> bool:
    """Lu avant d'encoder : le cœur refusera de poser pendant un scan, autant
    ne pas encoder l'album pour rien."""
    return (await session.execute(text("SELECT 1 FROM scan_runs WHERE status = 'running' LIMIT 1"))).first() is not None


async def apercu(album_id: int) -> dict | None:
    """Ce que ferait la conversion de l'album, lu sur la base et le disque,
    sans rien écrire. `None` si l'album n'existe pas."""
    disque = ctx().chemin_disque
    async with ctx().session() as s:
        album = await _album(s, album_id)
        if album is None:
            return None
        pistes = await _pistes(s, album_id)
        scan = await scan_en_cours(s)
    ffmpeg = conversion.ffmpeg_disponible()
    sondes = await asyncio.gather(*(conversion.sonder(disque(t["relative_path"])) for t in pistes)) if ffmpeg else [None] * len(pistes)
    decisions = []
    for t, sonde in zip(pistes, sondes):
        d = conversion.decider(t, sonde, lambda rel: disque(rel).exists(), ffmpeg=ffmpeg)
        if d.convertible:
            d.ecartes = await asyncio.to_thread(conversion.ecartes_de, disque(t["relative_path"]))
        decisions.append(d)
    convertibles = [d for d in decisions if d.convertible]
    return {
        "album_id": album_id,
        "dossier": album["folder_path"],
        "ffmpeg": ffmpeg,
        "mode_edition": ctx().mode_edition(),
        "scan_en_cours": scan,
        "pistes": [dict(d.vue(), motif_libelle=MOTIFS.get(d.motif)) for d in decisions],
        "a_convertir": len(convertibles),
        "corbeille": [d.source for d in convertibles],
    }


# ── Le type d'opération ──────────────────────────────────────────────────


def _attendues(op) -> list[int]:
    return sorted(int(i) for i in (op.get_params() or {}).get("track_ids") or [])


async def appliquer(op) -> dict:
    # Tout ce qui ferait refuser la pose se juge **avant** d'encoder : un
    # album qu'on ne pourra pas poser ne coûte pas des minutes de LAME.
    if not conversion.ffmpeg_disponible():
        raise RefusRemplacement("ffmpeg_absent", "ffmpeg et ffprobe sont introuvables")
    if not ctx().mode_edition():
        raise PermissionError("Edit mode is not enabled")
    async with ctx().session() as s:
        if await scan_en_cours(s):
            raise RefusRemplacement("scan_en_cours", "un scan tourne : la conversion attendra qu'il finisse")
    vue = await apercu(op.target_id)
    if vue is None:
        raise RefusRemplacement("album_introuvable", f"album {op.target_id}")
    convertibles = [p for p in vue["pistes"] if p["convertible"]]
    if sorted(p["track_id"] for p in convertibles) != _attendues(op) or not convertibles:
        raise RefusRemplacement("perime", "l'album a changé depuis l'aperçu")

    atelier = Path(tempfile.mkdtemp(prefix="unisson-convertir-"))
    try:
        remplacements = []
        for p in convertibles:
            cible = atelier / f"{p['track_id']}.mp3"
            await conversion.convertir(ctx().chemin_disque(p["source"]), cible, p["debit_cible"], p["duree"])
            remplacements.append({"track_id": p["track_id"], "fichier": str(cible), "nom": p["nom_cible"]})
        resultat = await ctx().remplacer_pistes(op, remplacements)
    finally:
        # Le dossier temporaire est le nôtre, hors de /music : le cœur a
        # **copié** ce qu'il a posé, ce qui reste ici n'est la musique de personne.
        shutil.rmtree(atelier, ignore_errors=True)
    resultat["converties"] = len(remplacements)
    return resultat


async def annuler(op) -> None:
    await ctx().retablir_pistes(op)


async def verifier(op, profondeur, _ctx_tampon) -> Verdict:
    """Le juge du tampon : `legere` ne lit que la base (jamais `/music`),
    `complete` refait l'aperçu sur le disque. Ce qu'il n'a pas su lire n'est
    jamais rangé : `indecidable`."""
    attendues = _attendues(op)
    async with ctx().session() as s:
        album = await _album(s, op.target_id)
        if album is None or album["trashed"]:
            return Verdict("sans_objet", "album_disparu", "l'album n'existe plus")
        lignes = await _lignes(s, attendues)
    if not attendues or len(lignes) != len(attendues) or any(l["album_id"] != op.target_id for l in lignes.values()):
        return Verdict("sans_objet", "pistes_disparues", "des pistes à convertir ne sont plus dans l'album")
    formats = {(l["format"] or "").upper() for l in lignes.values()}
    if formats == {"MP3"}:
        # Les mêmes lignes pointent déjà sur un MP3 : la conversion est faite.
        return Verdict("effet_present", "deja_converti", "ces pistes sont déjà en MP3")
    if formats != {"WMA"}:
        return Verdict("sans_objet", "perime", "une partie des pistes n'est plus en WMA")
    if profondeur == "complete":
        if not conversion.ffmpeg_disponible():
            return Verdict("indecidable", "ffmpeg_absent", "ffmpeg et ffprobe sont introuvables")
        vue = await apercu(op.target_id)
        par_id = {p["track_id"]: p for p in vue["pistes"]}
        if any(par_id.get(i, {}).get("motif") == "illisible" for i in attendues):
            return Verdict("indecidable", "illisible", "ffprobe n'a pas lu une piste : à rejuger plus tard")
        convertibles = sorted(p["track_id"] for p in vue["pistes"] if p["convertible"])
        if convertibles != attendues:
            return Verdict("sans_objet", "perime", "le disque a changé depuis l'aperçu")
    return Verdict("applicable")
