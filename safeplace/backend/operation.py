"""`safeplace.signaler` : le signalement que l'assistant propose en carte (#931).

L'assistant ne pose plus rien lui-même : il propose, la carte tamponne, et
c'est l'application du tampon qui inscrit le signalement, **confirmé** — avoir
validé la carte vaut confirmation. Annuler retire le signalement. La mise à
la corbeille reste un geste séparé, depuis la page Safeplace : une carte ne
porte qu'une décision.
"""

import json

from sqlalchemy import text
from unisson.plugin import TypeOperation, Verdict

from . import service

NOM = "safeplace.signaler"

CHAT = (
    "signaler un artiste de la bibliothèque dans la safeplace ; valider la carte confirme le "
    "signalement, rien ne part à la corbeille. targets = [artist_id] (depuis list_artists). "
    f"params: {{reasons (motif, avec ses sources), severity: {' | '.join(service.GRAVITES)}, "
    "source_url (facultatif)}. Vérifie d'abord avec safeplace_check_artist_status qu'il n'est "
    "pas déjà signalé."
)


def _params(op) -> dict:
    return json.loads(op.params_json or "{}")


def fabriquer(ctx) -> TypeOperation:
    async def appliquer(op) -> dict:
        p = _params(op)
        gravite = p.get("severity") or "autre"
        if gravite not in service.GRAVITES:
            raise ValueError(f"gravité inconnue : {gravite}")
        async with ctx.session() as s:
            if not await service.artiste_existe(s, op.target_id):
                raise ValueError(f"artiste {op.target_id} introuvable")
            await service.poser(
                s, artist_id=op.target_id, reasons=p.get("reasons") or "", severity=gravite,
                source_url=p.get("source_url") or None, flagged_by="serge", pending_review=0,
            )
            await s.commit()
        return {}

    async def annuler(op) -> None:
        async with ctx.session() as s:
            await service.retirer(s, op.target_id)
            await s.commit()

    async def verifier(op, profondeur, _contexte):
        # Déjà signalé et confirmé : l'effet est là. Une suggestion encore en
        # attente, elle, reste à confirmer — la carte s'applique.
        async with ctx.session() as s:
            ligne = (await s.execute(
                text("SELECT pending_review FROM artist_flags WHERE artist_id = :id"), {"id": op.target_id}
            )).first()
        if ligne is not None and not ligne.pending_review:
            return Verdict("effet_present", "deja_signale", "artiste déjà signalé dans la safeplace")
        return None

    return TypeOperation(
        NOM, appliquer, annuler, verifier, chat=CHAT, type_cible="artist", envoi_auto=False,
    )
