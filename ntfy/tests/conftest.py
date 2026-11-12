"""Les tests de ntfy tournent dans le harnais du cœur (≥ 0.11) : sa base de
test, son app, son vrai chargeur, sa vraie boucle du fil. Lancement : voir
`README.md` (« Tests »).

ntfy est joué par un **vrai serveur HTTP** local (`tests/aides.py`) : la
frontière simulée est le réseau, pas le plugin (#811).
"""

import shutil
import sys
from pathlib import Path

import pytest_asyncio
from sqlalchemy import text

PLUGIN = Path(__file__).resolve().parents[1]
# `ntfy.tests.aides` et `ntfy.backend` s'importent depuis le dossier du dépôt ;
# `unisson.plugin` n'existe qu'une fois la façade publiée par le chargeur.
sys.path.insert(0, str(PLUGIN.parent))
from backend.plugins.chargeur import _publier_facade  # noqa: E402

_publier_facade()
ID = "ntfy"


async def _retirer_schema():
    from backend.tests.conftest import test_engine

    async with test_engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "plugin_{ID}" CASCADE'))


@pytest_asyncio.fixture
async def ntfy_serveur():
    from ntfy.tests.aides import FauxNtfy

    serveur = FauxNtfy()
    yield serveur
    serveur.fermer()


@pytest_asyncio.fixture
async def charge(tmp_path, monkeypatch, client):
    """Le plugin copié dans un dossier de plugins vide et chargé (inactif) :
    on règle, puis on active."""
    from backend.config import settings
    from backend.main import app
    from backend.plugins import chargeur, etat, registres
    from backend.services import fil, runtime_settings

    await _retirer_schema()
    monkeypatch.setattr(runtime_settings, "_cache", {})
    fil.oublier()
    dossier = tmp_path / "plugins"
    dossier.mkdir()
    monkeypatch.setattr(settings, "plugins_dir", dossier)
    shutil.copytree(PLUGIN, dossier / ID, ignore=shutil.ignore_patterns("tests", "node_modules", "__pycache__"))
    await chargeur.charger(app)
    yield client
    await chargeur.arreter_tout()
    etat.vider()
    registres.canaux_notification._inscriptions.clear()
    fil.oublier()
    await _retirer_schema()
