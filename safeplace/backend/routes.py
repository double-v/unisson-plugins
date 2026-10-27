"""Les routes du plugin, montées par le cœur sous `/api/plugins/safeplace/`."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import service

router = APIRouter()
_ctx = {}


def brancher(ctx) -> APIRouter:
    _ctx["ctx"] = ctx
    return router


def _session():
    return _ctx["ctx"].session()


class SignalementIn(BaseModel):
    artist_id: int
    reasons: str = ""
    severity: Literal["accusé", "condamné", "autre"] = "autre"
    source_url: str | None = None
    pending_review: int = 0
    flagged_by: str = "user"


@router.get("/flags")
async def lister(
    genre_id: int | None = None,
    severity: str | None = None,
    pending_review: int | None = None,
    limit: int = 100,
    offset: int = 0,
):
    # Un filtre inconnu rend 422, jamais la liste entière (règle du cœur, #414).
    if severity and severity not in service.GRAVITES:
        raise HTTPException(422, f"gravité inconnue : {severity}")
    if pending_review not in (None, 0, 1):
        raise HTTPException(422, "pending_review vaut 0 ou 1")
    async with _session() as s:
        items, total = await service.lister(
            s, genre_id=genre_id, severity=severity, pending_review=pending_review, limit=limit, offset=offset
        )
    return {"items": items, "total": total, "offset": offset, "limit": min(limit, 200)}


@router.get("/flags/{artist_id}")
async def lire(artist_id: int):
    """Le signalement d'un artiste ; `null` s'il n'en a pas (cas majoritaire)."""
    async with _session() as s:
        return await service.lire(s, artist_id)


@router.post("/flags", status_code=201)
async def poser(corps: SignalementIn):
    async with _session() as s:
        if not await service.artiste_existe(s, corps.artist_id):
            raise HTTPException(404, f"artiste {corps.artist_id} introuvable")
        await service.poser(s, **corps.model_dump())
        await s.commit()
        return await service.lire(s, corps.artist_id)


@router.put("/flags/{artist_id}/confirm")
async def confirmer(artist_id: int):
    async with _session() as s:
        if not await service.confirmer(s, artist_id):
            raise HTTPException(404, "signalement introuvable")
        await s.commit()
        return await service.lire(s, artist_id)


@router.delete("/flags/{artist_id}")
async def retirer(artist_id: int):
    async with _session() as s:
        if not await service.retirer(s, artist_id):
            raise HTTPException(404, "signalement introuvable")
        await s.commit()
    return {"ok": True}
