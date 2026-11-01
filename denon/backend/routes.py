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


class CorpsInvalide(Exception):
    def __init__(self, statut: int, code: str):
        self.statut, self.code = statut, code


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
            except CorpsInvalide as e:
                return JSONResponse({"error": e.code}, status_code=e.statut)

        return gestionnaire


def garde_du_jeton(jeton: Callable[[], str]):
    """La dépendance qui exige `Authorization: Bearer <jeton>` si un jeton
    est réglé ; partagée par l'API de denon-api et les routes du réveil."""

    def garde(request: Request) -> None:
        attendu = jeton()
        if not attendu:
            return
        # En octets : compare_digest lève sur une chaîne non ASCII. Starlette
        # décode les en-têtes en latin-1 : ré-encoder rend les octets reçus.
        recu = request.headers.get("authorization", "").encode("latin-1")
        if not secrets.compare_digest(recu, f"Bearer {attendu}".encode("utf-8")):
            raise NonAutorise

    return garde


async def corps(request: Request) -> dict:
    """Comme Fastify : un corps présent doit être du JSON valide (sinon
    400, ou 415 pour un autre type), jamais lu comme un corps vide — un
    `on=true` en formulaire éteindrait l'ampli."""
    brut = await request.body()
    if not brut:
        return {}
    if "json" not in request.headers.get("content-type", "application/json").lower():
        raise CorpsInvalide(415, "unsupported_media_type")
    try:
        valeur = json.loads(brut)
    except ValueError:
        raise CorpsInvalide(400, "invalid_json") from None
    return valeur if isinstance(valeur, dict) else {}


def fabriquer(lien: Lien, jeton: Callable[[], str]) -> APIRouter:
    router = APIRouter(route_class=_Route)
    pilote = lien.pilote
    protege = [Depends(garde_du_jeton(jeton))]

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
        return await envoyer(pilote.alimentation(_vrai((await corps(request)).get("on"))))

    @router.post("/api/mute", dependencies=protege)
    async def sourdine(request: Request):
        return await envoyer(pilote.sourdine(_vrai((await corps(request)).get("muted"))))

    @router.post("/api/source", dependencies=protege)
    async def source(request: Request):
        valeur = (await corps(request)).get("source")
        # String(x || '') de denon-api : false, 0, null, "" donnent "".
        source = ("" if not _vrai(valeur) else "TRUE" if valeur is True else str(valeur)).upper()
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


def _vrai(valeur) -> bool:
    """`Boolean(x)` de JavaScript : une liste ou un objet, même vides, sont vrais."""
    return True if isinstance(valeur, (list, dict)) else bool(valeur)


def _nombre(valeur) -> float | None:
    """`Number(x)` de denon-api, sans ses pièges (`null` → 0, `true` → 1)."""
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        n = float(valeur)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None
