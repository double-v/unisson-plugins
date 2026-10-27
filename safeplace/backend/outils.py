"""L'outil que le plugin prête à l'assistant : vérifier, en lecture seule.

L'assistant ne décide de rien. Pour signaler, il propose une carte
`safeplace.signaler` par `propose_action` (#931) : le seul chemin vers le
tampon, celui du cœur. L'ancien `safeplace_suggest_addition`, qui écrivait
une suggestion en attente sans passer par l'opérateur, est retiré.
"""

from rapidfuzz import process
from sqlalchemy import text

from . import service

VERIFIER = {
    "type": "function",
    "function": {
        "name": "safeplace_check_artist_status",
        "description": (
            "Vérifie si un artiste est signalé dans la safeplace. Rend in_safeplace=true avec "
            "les raisons et la gravité s'il l'est, false sinon (avec son artist_id s'il est dans la "
            "bibliothèque, cible d'une carte safeplace.signaler). Lecture seule — si absent, "
            "complète avec web_search pour du contexte, sans conclure sans source."
        ),
        "parameters": {
            "type": "object",
            "properties": {"artist_name": {"type": "string", "description": "Nom de l'artiste à vérifier"}},
            "required": ["artist_name"],
        },
    },
}

async def _trouver(session, nom: str, requete: str) -> tuple[int, str] | None:
    """L'artiste le plus proche (rapidfuzz ≥ 80 sur le nom de dossier), ou rien."""
    lignes = (await session.execute(text(requete))).all()
    if not lignes:
        return None
    choix = {l.id: l.folder_name for l in lignes}
    trouve = process.extractOne(nom, choix, score_cutoff=80)
    if trouve is None:
        return None
    return trouve[2], choix[trouve[2]]


def fabriquer(ctx):
    async def verifier(args: dict) -> dict:
        nom = (args.get("artist_name") or "").strip()
        if not nom:
            return {"error": "artist_name requis"}
        async with ctx.session() as s:
            trouve = await _trouver(
                s, nom,
                "SELECT a.id, a.folder_name FROM artist_flags f JOIN artists a ON a.id = f.artist_id "
                "WHERE a.trashed = 0",
            )
            if trouve is None:
                # L'id de l'artiste, s'il est dans la bibliothèque : c'est la
                # cible d'une carte `safeplace.signaler`.
                local = await _trouver(s, nom, "SELECT id, folder_name FROM artists WHERE trashed = 0")
                if local is None:
                    return {"in_safeplace": False}
                return {"in_safeplace": False, "artist_id": local[0], "artist_name": local[1]}
            item = await service.lire(s, trouve[0])
        return {
            "in_safeplace": True,
            "artist_id": item["artist_id"],
            "artist_name": item["artist_name"],
            "reasons": item["reasons"],
            "severity": item["severity"],
            "source_url": item["source_url"],
            "flagged_by": item["flagged_by"],
            "pending_review": item["pending_review"],
        }

    return verifier
