"""Les routes du plugin : l'aperçu, en lecture seule.

Tamponner passe par la route du cœur (`POST /api/operations/staged`) : un
seul chemin vers le tampon, et l'écran lit l'état qu'elle rend.
"""

from fastapi import APIRouter, HTTPException

from . import service

router = APIRouter()


@router.get("/albums/{album_id}/apercu")
async def apercu(album_id: int):
    vue = await service.apercu(album_id)
    if vue is None:
        raise HTTPException(404, f"album {album_id} introuvable")
    return vue
