"""Les signalements : une ligne par artiste dans `artist_flags`.

Un signalement n'a aucun effet sur les fichiers. La mise à la corbeille
d'un artiste reste une opération **du cœur** (`trash_artist`) : le plugin
la propose au tampon avec la provenance `safeplace`, il ne la possède pas.

Le plugin n'importe du cœur que `unisson.plugin` : il lit les tables de la
bibliothèque (`artists`, `albums`, `genres`, `tracks`) en SQL, sans leurs
modèles. Les horodatages sont des chaînes ISO, comme partout dans unisson.
"""

from datetime import datetime, timezone

from sqlalchemy import text

GRAVITES = ("accusé", "condamné", "autre")

_NOM = (
    "COALESCE(NULLIF(trim(a.name_from_nfo), ''), NULLIF(trim(a.name_from_tags), ''), a.folder_name)"
)

_LIGNE = f"""
    SELECT f.artist_id, {_NOM} AS artist_name, a.genre_id, g.name AS genre_name,
           f.reasons, f.severity, f.source_url, f.flagged_by, f.flagged_at, f.pending_review
    FROM plugin_safeplace.artist_flags f
    JOIN artists a ON a.id = f.artist_id
    LEFT JOIN genres g ON g.id = a.genre_id
"""


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _stats(session, ids: list[int]) -> dict[int, dict]:
    """Albums hors corbeille et leur poids, par artiste, en deux requêtes."""
    if not ids:
        return {}
    albums = await session.execute(
        text(
            "SELECT artist_id, count(*) FROM albums "
            "WHERE artist_id = ANY(:ids) AND trashed = 0 GROUP BY artist_id"
        ),
        {"ids": ids},
    )
    nb = {aid: int(n) for aid, n in albums}
    tailles = await session.execute(
        text(
            "SELECT al.artist_id, coalesce(sum(t.file_size_bytes), 0) FROM albums al "
            "JOIN tracks t ON t.album_id = al.id "
            "WHERE al.artist_id = ANY(:ids) AND al.trashed = 0 GROUP BY al.artist_id"
        ),
        {"ids": ids},
    )
    poids = {aid: int(s) for aid, s in tailles}
    return {i: {"album_count": nb.get(i, 0), "total_size_bytes": poids.get(i, 0)} for i in ids}


def _item(ligne, stats: dict) -> dict:
    d = dict(ligne._mapping)
    d["reasons"] = d["reasons"] or ""
    d.update(stats.get(d["artist_id"], {"album_count": 0, "total_size_bytes": 0}))
    return d


async def lister(session, *, genre_id=None, severity=None, pending_review=None, limit=100, offset=0):
    """Les signalements enrichis, paginés ; un filtre ne s'ajoute que s'il est actif."""
    limit = min(limit, 200)
    conditions, valeurs = [], {"limit": limit, "offset": offset}
    if genre_id is not None:
        conditions.append("a.genre_id = :genre_id")
        valeurs["genre_id"] = genre_id
    if severity:
        conditions.append("f.severity = :severity")
        valeurs["severity"] = severity
    if pending_review is not None:
        conditions.append("f.pending_review = :pending_review")
        valeurs["pending_review"] = pending_review
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = (
        await session.execute(
            text(f"SELECT count(*) FROM plugin_safeplace.artist_flags f JOIN artists a ON a.id = f.artist_id{where}"),
            valeurs,
        )
    ).scalar_one()
    lignes = (
        await session.execute(
            text(_LIGNE + where + " ORDER BY f.flagged_at DESC, f.id DESC LIMIT :limit OFFSET :offset"),
            valeurs,
        )
    ).all()
    stats = await _stats(session, [l.artist_id for l in lignes])
    return [_item(l, stats) for l in lignes], int(total)


async def lire(session, artist_id: int) -> dict | None:
    ligne = (await session.execute(text(_LIGNE + " WHERE f.artist_id = :id"), {"id": artist_id})).first()
    if ligne is None:
        return None
    return _item(ligne, await _stats(session, [artist_id]))


async def artiste_existe(session, artist_id: int) -> bool:
    return (await session.execute(text("SELECT 1 FROM artists WHERE id = :id"), {"id": artist_id})).first() is not None


async def poser(session, *, artist_id, reasons="", severity="autre", source_url=None,
                flagged_by="user", pending_review=0) -> None:
    """Crée ou met à jour le signalement d'un artiste (une ligne par artiste)."""
    await session.execute(
        text(
            "INSERT INTO plugin_safeplace.artist_flags (artist_id, reasons, severity, source_url, flagged_by, flagged_at, pending_review) "
            "VALUES (:artist_id, :reasons, :severity, :source_url, :flagged_by, :flagged_at, :pending_review) "
            "ON CONFLICT (artist_id) DO UPDATE SET reasons = excluded.reasons, severity = excluded.severity, "
            "source_url = excluded.source_url, pending_review = excluded.pending_review"
        ),
        {
            "artist_id": artist_id, "reasons": reasons, "severity": severity, "source_url": source_url,
            "flagged_by": flagged_by, "flagged_at": maintenant(), "pending_review": pending_review,
        },
    )


async def confirmer(session, artist_id: int) -> bool:
    r = await session.execute(
        text("UPDATE plugin_safeplace.artist_flags SET pending_review = 0 WHERE artist_id = :id"), {"id": artist_id}
    )
    return r.rowcount > 0


async def retirer(session, artist_id: int) -> bool:
    r = await session.execute(text("DELETE FROM plugin_safeplace.artist_flags WHERE artist_id = :id"), {"id": artist_id})
    return r.rowcount > 0
