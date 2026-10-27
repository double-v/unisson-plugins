"""Les tests du plugin tournent dans le harnais du cœur : sa base de test,
son app, son vrai chargeur. Lancement : voir `README.md` (« Tests »).

Le plugin est copié dans un dossier de plugins vide, chargé, activé ; à la
fin, son schéma `plugin_safeplace` est retiré — le cœur ne le connaît pas,
et `drop_all` buterait sur la clé étrangère vers `artists`.
"""

import shutil
from pathlib import Path

import pytest_asyncio
from sqlalchemy import text

PLUGIN = Path(__file__).resolve().parents[1]


async def _retirer_tables():
    from backend.tests.conftest import test_engine

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS plugin_safeplace CASCADE"))
        # Une suite d'avant la 1.2.0 a pu les laisser dans `public`.
        await conn.execute(text("DROP TABLE IF EXISTS public.artist_flags CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_safeplace"))


@pytest_asyncio.fixture
async def safeplace(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.main import app
    from backend.plugins import chargeur, etat

    await _retirer_tables()
    monkeypatch.setattr(settings, "plugins_dir", tmp_path)
    shutil.copytree(PLUGIN, tmp_path / "safeplace", ignore=shutil.ignore_patterns("tests", "node_modules", "__pycache__"))
    await chargeur.charger(app)
    await chargeur.activer("safeplace")
    yield
    chargeur.arreter_tout()
    etat.vider()
    await _retirer_tables()
