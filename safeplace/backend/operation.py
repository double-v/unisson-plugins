"""`safeplace.signaler` : le signalement que l'assistant propose en carte (#931).

L'assistant ne pose plus rien lui-même : il propose, la carte tamponne, et
c'est l'application du tampon qui inscrit le signalement, **confirmé** — avoir
validé la carte vaut confirmation. La mise à
la corbeille reste un geste séparé, depuis la page Safeplace : une carte ne
porte qu'une décision.

Défaire ramène à l'état d'avant, sans instantané : un signalement que la
carte a **créé** porte `flagged_by="carte"` et se retire ; une suggestion en
attente que la carte a seulement **confirmée** garde ses motifs (la carte ne
les réécrit pas) et retourne en attente.
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


PAR_CARTE = "carte"


async def _artiste_present(session, artist_id: int) -> bool:
    return (await session.execute(
        text("SELECT 1 FROM artists WHERE id = :id AND trashed = 0"), {"id": artist_id}
    )).first() is not None


def _params(op) -> dict:
    return json.loads(op.params_json or "{}")


def fabriquer(ctx) -> TypeOperation:
    async def appliquer(op) -> dict:
        p = _params(op)
        gravite = p.get("severity") or "autre"
        if gravite not in service.GRAVITES:
            raise ValueError(f"gravité inconnue : {gravite}")
        async with ctx.session() as s:
            if not await _artiste_present(s, op.target_id):
                raise ValueError(f"artiste {op.target_id} introuvable ou à la corbeille")
            if await service.lire(s, op.target_id) is not None:
                # Une suggestion en attente : on la confirme, ses motifs restent.
                await service.confirmer(s, op.target_id)
            else:
                await service.poser(
                    s, artist_id=op.target_id, reasons=p.get("reasons") or "", severity=gravite,
                    source_url=p.get("source_url") or None, flagged_by=PAR_CARTE, pending_review=0,
                )
            await s.commit()
        return {}

    async def annuler(op) -> None:
        async with ctx.session() as s:
            item = await service.lire(s, op.target_id)
            if item is not None and item["flagged_by"] == PAR_CARTE:
                await service.retirer(s, op.target_id)
            elif item is not None:
                await s.execute(
                    text("UPDATE plugin_safeplace.artist_flags SET pending_review = 1 WHERE artist_id = :id"), {"id": op.target_id}
                )
            await s.commit()

    async def verifier(op, profondeur, _contexte):
        # Déjà signalé et confirmé : l'effet est là. Une suggestion encore en
        # attente, elle, reste à confirmer — la carte s'applique.
        async with ctx.session() as s:
            if not await _artiste_present(s, op.target_id):
                return Verdict("sans_objet", "artiste_absent", "artiste disparu ou à la corbeille")
            ligne = (await s.execute(
                text("SELECT pending_review FROM plugin_safeplace.artist_flags WHERE artist_id = :id"), {"id": op.target_id}
            )).first()
        if ligne is not None and not ligne.pending_review:
            return Verdict("effet_present", "deja_signale", "artiste déjà signalé dans la safeplace")
        return None

    return TypeOperation(
        NOM, appliquer, annuler, verifier, chat=CHAT, type_cible="artist", envoi_auto=False,
    )
