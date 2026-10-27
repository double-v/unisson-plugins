"""Les deux outils que le plugin prête à l'assistant.

L'assistant ne décide de rien : `safeplace_suggest_addition` pose un
signalement **en attente** (`pending_review=1`, `flagged_by="serge"`), que
l'opérateur confirme ou rejette depuis la page Safeplace. Une suggestion en
attente n'est pas un signalement acté.
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
            "les raisons et la gravité s'il l'est, false sinon. Lecture seule — si absent, "
            "complète avec web_search pour du contexte, sans conclure sans source."
        ),
        "parameters": {
            "type": "object",
            "properties": {"artist_name": {"type": "string", "description": "Nom de l'artiste à vérifier"}},
            "required": ["artist_name"],
        },
    },
}

SUGGERER = {
    "type": "function",
    "function": {
        "name": "safeplace_suggest_addition",
        "description": (
            "Suggère de signaler un artiste de la bibliothèque dans la safeplace. Le signalement "
            "reste en attente : l'opérateur le confirme ou le rejette depuis la page Safeplace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string", "description": "Nom de l'artiste"},
                "reasons": {"type": "string", "description": "Raisons du signalement, avec leurs sources"},
                "severity": {"type": "string", "enum": list(service.GRAVITES)},
                "source_url": {"type": "string", "description": "URL de la source (facultatif)"},
            },
            "required": ["artist_name", "reasons", "severity"],
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
                return {"in_safeplace": False}
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

    async def suggerer(args: dict) -> dict:
        nom = (args.get("artist_name") or "").strip()
        if not nom:
            return {"error": "artist_name requis"}
        gravite = args.get("severity") or "autre"
        if gravite not in service.GRAVITES:
            return {"error": f"gravité inconnue : {gravite}"}
        async with ctx.session() as s:
            trouve = await _trouver(s, nom, "SELECT id, folder_name FROM artists WHERE trashed = 0")
            if trouve is None:
                return {"error": f"Artiste « {nom} » introuvable dans la bibliothèque (aucun nom ≥ 80)."}
            deja = await service.lire(s, trouve[0])
            if deja is not None:
                # Ne jamais rétrograder un signalement acté en suggestion.
                return {"status": "already_flagged", "artist_id": trouve[0], "pending_review": deja["pending_review"]}
            await service.poser(
                s, artist_id=trouve[0], reasons=args.get("reasons") or "", severity=gravite,
                source_url=args.get("source_url") or None, flagged_by="serge", pending_review=1,
            )
            await s.commit()
        return {"status": "suggested", "artist_id": trouve[0], "artist_name": trouve[1]}

    return verifier, suggerer
