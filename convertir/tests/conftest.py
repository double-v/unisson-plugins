"""Les tests du plugin tournent dans le harnais du cœur : sa base de test,
son app, son vrai chargeur. Lancement : voir `README.md` (« Tests »).

Le plugin est copié dans un dossier de plugins vide, chargé, activé. Il n'a
pas de table : rien à retirer à la fin, sinon son schéma vide.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

PLUGIN = Path(__file__).resolve().parents[1]

async def _retirer_schema():
    from backend.tests.conftest import test_engine

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS plugin_convertir CASCADE"))


@pytest_asyncio.fixture
async def convertir(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.main import app
    from backend.plugins import chargeur, etat

    await _retirer_schema()
    dossier = tmp_path / "plugins"
    dossier.mkdir()
    monkeypatch.setattr(settings, "plugins_dir", dossier)
    shutil.copytree(PLUGIN, dossier / "convertir", ignore=shutil.ignore_patterns("tests", "node_modules", "__pycache__"))
    await chargeur.charger(app)
    await chargeur.activer("convertir")
    yield
    await chargeur.arreter_tout()
    etat.vider()
    await _retirer_schema()


@pytest.fixture
def disque(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.services import edit_mode

    racine = tmp_path / "music"
    racine.mkdir()
    monkeypatch.setattr(settings, "edit_mode", True)
    monkeypatch.setattr(settings, "music_root", racine)
    monkeypatch.setattr(edit_mode, "_writable", True)
    return racine


@pytest.fixture
def wma():
    return fabriquer_wma


def fabriquer_wma(chemin: Path, *, debit: int = 192, duree: float = 2.0, tags: dict | None = None,
                  image: bytes | None = None) -> Path:
    """Un vrai WMA (wmav2), tagué en ASF comme le ferait Windows Media Player."""
    from mutagen.asf import ASF, ASFByteArrayAttribute

    chemin.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={duree}",
         "-ac", "2", "-c:a", "wmav2", "-b:a", f"{debit}k", str(chemin)],
        check=True,
    )
    f = ASF(str(chemin))
    for cle, valeur in (tags or {}).items():
        f[cle] = [valeur]
    if image is not None:
        mime = "image/jpeg".encode("utf-16-le") + b"\x00\x00"
        desc = b"\x00\x00"
        brut = bytes([3]) + len(image).to_bytes(4, "little") + mime + desc + image
        f["WM/Picture"] = [ASFByteArrayAttribute(brut)]
    f.save()
    return chemin
