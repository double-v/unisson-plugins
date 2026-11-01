"""L'écoute à part, sur l'ancien port de `denon-api` (8100 chez nous).

Le même routeur que sous `/api/plugins/denon/`, servi seul par un second
serveur uvicorn dans le processus d'unisson. Deux pièges d'uvicorn évités :

- `serve()` capture SIGINT/SIGTERM : un second serveur les volerait à celui
  d'unisson. On lui laisse les signaux (`capture_signals` neutralisé) ; il
  s'arrête quand la tâche du plugin est annulée ;
- un port déjà pris fait `sys.exit(1)` au démarrage, qui remonterait hors de
  la boucle et ferait tomber unisson. Le socket est donc réservé ici : un
  échec se journalise, et le plugin continue sous `/api/plugins/denon/`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket

import uvicorn
from fastapi import APIRouter, FastAPI


class _Serveur(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self):
        yield


def reserver(port: int, hote: str = "0.0.0.0") -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((hote, port))
    except OSError:
        s.close()
        raise
    s.listen(128)
    s.setblocking(False)
    return s


async def servir(router: APIRouter, port: int, journal: logging.Logger, hote: str = "0.0.0.0") -> None:
    if not port:
        return
    try:
        sock = reserver(port, hote)
    except OSError as e:
        journal.error("écoute à part impossible sur le port %s : %s (les routes restent sous /api/plugins/denon/)", port, e)
        return
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)
    serveur = _Serveur(uvicorn.Config(app, lifespan="off", log_level="warning", access_log=False, timeout_graceful_shutdown=2))
    journal.info("API denon-api servie aussi sur le port %s", port)
    tache = asyncio.create_task(serveur.serve(sockets=[sock]))
    try:
        await asyncio.shield(tache)
    except asyncio.CancelledError:
        # Arrêt propre : uvicorn ferme ses connexions, puis on rend la main.
        serveur.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(tache, 5)
        raise
    finally:
        sock.close()
