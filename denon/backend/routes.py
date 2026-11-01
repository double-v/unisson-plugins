"""L'API de `denon-api`, à l'identique : chemins, corps, réponses, jeton.

Montée par le cœur sous `/api/plugins/denon/` et, si `port_ecoute` est
réglé, servie aussi seule sur ce port (`ecoute.py`) : Hublot et les autres
clients de `denon-api` basculent sans changer une ligne. Les tests de
non-régression rejouent les appels du client Denon de Hublot.
"""

from __future__ import annotations

import json
import math
import re
import secrets
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .lien import Injoignable, Lien

_SOURCE = re.compile(r"[A-Z0-9_]{1,12}")


class NonAutorise(Exception):
    pass


class _Route(APIRoute):
    """Rend le refus du jeton au format de denon-api. Le routeur est monté
    dans l'app du cœur : il ne peut pas y poser de gestionnaire d'erreur."""

    def get_route_handler(self):
        traiter = super().get_route_handler()

        async def gestionnaire(request: Request):
            try:
                return await traiter(request)
            except NonAutorise:
                return JSONResponse({"error": "unauthorized"}, status_code=401)

        return gestionnaire


def fabriquer(lien: Lien, jeton: Callable[[], str]) -> APIRouter:
    router = APIRouter(route_class=_Route)
    pilote = lien.pilote

    def garde(request: Request) -> None:
        attendu = jeton()
        if attendu and not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {attendu}"):
            raise NonAutorise

    protege = [Depends(garde)]

    async def corps(request: Request) -> dict:
        brut = await request.body()
        try:
            valeur = json.loads(brut) if brut else {}
        except ValueError:
            return {}
        return valeur if isinstance(valeur, dict) else {}

    async def envoyer(commande: str):
        try:
            await lien.envoyer(commande)
        except (Injoignable, ValueError) as e:
            return JSONResponse({"error": "denon_unreachable", "message": str(e)}, status_code=503)
        return {"accepted": True, "command": commande}

    @router.get("/healthz")
    async def sante():
        return {"ok": True, "denon": lien.connecte}

    @router.get("/api/state", dependencies=protege)
    async def etat():
        return {**lien.etat, "host": lien.config.hote or None, "port": lien.config.port}

    @router.get("/api/queue", dependencies=protege)
    async def file():
        return {"pending": lien.en_attente, "cadenceMs": round(lien.config.cadence_s * 1000)}

    @router.post("/api/command", dependencies=protege)
    async def commande(request: Request):
        commande = (await corps(request)).get("command")
        if not isinstance(commande, str):
            return JSONResponse({"error": "command_required"}, status_code=400)
        try:
            await lien.envoyer(commande)
        except (Injoignable, ValueError) as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        return {"accepted": True, "command": commande}

    @router.post("/api/power", dependencies=protege)
    async def alimentation(request: Request):
        return await envoyer(pilote.alimentation(bool((await corps(request)).get("on"))))

    @router.post("/api/mute", dependencies=protege)
    async def sourdine(request: Request):
        return await envoyer(pilote.sourdine(bool((await corps(request)).get("muted"))))

    @router.post("/api/source", dependencies=protege)
    async def source(request: Request):
        valeur = (await corps(request)).get("source")
        source = str(valeur if valeur is not None else "").upper()
        if not _SOURCE.fullmatch(source):
            return JSONResponse({"error": "invalid_source"}, status_code=400)
        return await envoyer(pilote.source(source))

    @router.post("/api/volume", dependencies=protege)
    async def volume(request: Request):
        db = _nombre((await corps(request)).get("db"))
        if db is None or not -80 <= db <= 18:
            return JSONResponse({"error": "invalid_volume"}, status_code=400)
        return await envoyer(pilote.volume(db))

    @router.post("/api/volume/up", dependencies=protege)
    async def plus():
        return await envoyer(pilote.volume_plus())

    @router.post("/api/volume/down", dependencies=protege)
    async def moins():
        return await envoyer(pilote.volume_moins())

    return router


def _nombre(valeur) -> float | None:
    """`Number(x)` de denon-api, sans ses pièges (`null` → 0, `true` → 1)."""
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        n = float(valeur)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None
