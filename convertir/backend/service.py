"""L'aperçu d'un album et le type d'opération `convertir.mp3` (#950).

Le plan est **recalculé** à l'application, sur le disque courant, et doit
porter les mêmes pistes que celui qu'on a tamponné : un album rescanné,
retagué ou déjà converti entre-temps donne un refus `perime`, jamais une
conversion de ce qu'on n'a pas vu.

Rien n'est déplacé ici : les MP3 sont préparés dans un dossier temporaire,
puis `ctx.remplacer_pistes` les pose et met les WMA à la corbeille (le seul
chemin du cœur vers la corbeille), tout ou rien. La révocation est
`ctx.retablir_pistes`.
"""

from __future__ import annotations

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


async def apercu(album_id: int) -> dict | None:
    """Ce que ferait la conversion de l'album, lu sur la base et le disque,
    sans rien écrire. `None` si l'album n'existe pas."""
    racine = ctx().racine_musique()
    async with ctx().session() as s:
        album = await _album(s, album_id)
        if album is None:
            return None
        pistes = await _pistes(s, album_id)
    decisions = []
    for t in pistes:
        sonde = await conversion.sonder(racine / t["relative_path"]) if conversion.ffmpeg_disponible() else None
        decisions.append(conversion.decider(t, sonde, lambda rel: (racine / rel).exists()))
    convertibles = [d for d in decisions if d.convertible]
    return {
        "album_id": album_id,
        "dossier": album["folder_path"],
        "ffmpeg": conversion.ffmpeg_disponible(),
        "mode_edition": ctx().mode_edition(),
        "pistes": [dict(d.vue(), motif_libelle=MOTIFS.get(d.motif)) for d in decisions],
        "a_convertir": len(convertibles),
        "corbeille": [d.source for d in convertibles],
    }


# ── Le type d'opération ──────────────────────────────────────────────────


def _attendues(op) -> list[int]:
    return sorted(int(i) for i in (op.get_params() or {}).get("track_ids") or [])


async def appliquer(op) -> dict:
    if not conversion.ffmpeg_disponible():
        raise RefusRemplacement("ffmpeg_absent", "ffmpeg et ffprobe sont introuvables")
    if not ctx().mode_edition():
        # Avant d'encoder : un album qu'on ne pourra pas poser ne coûte rien.
        raise PermissionError("Edit mode is not enabled")
    vue = await apercu(op.target_id)
    if vue is None:
        raise RefusRemplacement("album_introuvable", f"album {op.target_id}")
    convertibles = [p for p in vue["pistes"] if p["convertible"]]
    if sorted(p["track_id"] for p in convertibles) != _attendues(op) or not convertibles:
        raise RefusRemplacement("perime", "l'album a changé depuis l'aperçu")

    racine = ctx().racine_musique()
    async with ctx().session() as s:
        durees = {t["id"]: t["duration_seconds"] for t in await _pistes(s, op.target_id)}
    atelier = Path(tempfile.mkdtemp(prefix="unisson-convertir-"))
    try:
        remplacements = []
        for p in convertibles:
            source = racine / p["source"]
            cible = atelier / f"{p['track_id']}.mp3"
            duree = durees.get(p["track_id"]) or (await conversion.sonder(source) or {}).get("duree")
            await conversion.convertir(source, cible, p["debit_cible"], duree)
            remplacements.append({"track_id": p["track_id"], "fichier": str(cible), "nom": p["nom_cible"]})
        resultat = await ctx().remplacer_pistes(op, remplacements)
    finally:
        # Le dossier temporaire est le nôtre, hors de /music : ce qui y reste
        # (un MP3 rendu par un échec) n'est la musique de personne.
        shutil.rmtree(atelier, ignore_errors=True)
    resultat["converties"] = len(remplacements)
    return resultat


async def annuler(op) -> None:
    await ctx().retablir_pistes(op)


async def verifier(op, profondeur, _ctx_tampon) -> Verdict:
    """Le juge du tampon : `legere` ne lit que la base (jamais `/music`),
    `complete` refait l'aperçu sur le disque."""
    attendues = _attendues(op)
    async with ctx().session() as s:
        album = await _album(s, op.target_id)
        if album is None or album["trashed"]:
            return Verdict("sans_objet", "album_disparu", "l'album n'existe plus")
        presentes = sorted(t["id"] for t in await _pistes(s, op.target_id))
    if not presentes:
        return Verdict("effet_present", "deja_converti", "l'album n'a plus de piste WMA")
    if not set(attendues) <= set(presentes):
        return Verdict("sans_objet", "perime", "les pistes ont changé depuis l'aperçu")
    if profondeur == "complete":
        if not conversion.ffmpeg_disponible():
            return Verdict("indecidable", "ffmpeg_absent", "ffmpeg et ffprobe sont introuvables")
        vue = await apercu(op.target_id)
        convertibles = sorted(p["track_id"] for p in vue["pistes"] if p["convertible"])
        if convertibles != attendues:
            return Verdict("sans_objet", "perime", "le disque a changé depuis l'aperçu")
    return Verdict("applicable")
