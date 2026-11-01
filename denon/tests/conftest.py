"""Les tests du plugin tournent dans le harnais du cœur (voir `README.md`).

Les faux sont posés à la frontière : `faux_ampli` est un vrai serveur TCP
qui parle comme un AVR (trames terminées par `\\r`), jamais un faux lien.
"""

import asyncio
import re
import shutil
import socket
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

PLUGIN = Path(__file__).resolve().parents[1]
# Les tests unitaires importent le paquet du plugin comme `denon.backend`,
# avec la façade `unisson.plugin` publiée comme le fait le chargeur.
sys.path.insert(0, str(PLUGIN.parent))
from backend.plugins.chargeur import _publier_facade  # noqa: E402

_publier_facade()


_ECHO = re.compile(r"PWON|PWSTANDBY|MV\d{2,3}|SI[A-Z0-9]+")


class FauxAmpli:
    def __init__(self):
        self.recues: list[tuple[float, str]] = []
        self.connexions = 0
        self.fermetures = 0
        self._clients: list[asyncio.StreamWriter] = []
        self.serveur = None
        self.port = 0
        # Comme un vrai AVR : il renvoie l'état que change une commande
        # (`MV455` → `MV455`), ce que la séance guette pour la montée du volume.
        self.echo = False
        self.sans_echo: set[str] = set()  # commandes dont l'écho se perd

    async def demarrer(self, port: int = 0):
        self.serveur = await asyncio.start_server(self._client, "127.0.0.1", port)
        self.port = self.serveur.sockets[0].getsockname()[1]

    async def _client(self, lecteur, ecrivain):
        self.connexions += 1
        self._clients.append(ecrivain)
        tampon = ""
        try:
            while morceau := await lecteur.read(1024):
                tampon += morceau.decode()
                *lignes, tampon = tampon.split("\r")
                self.recues += [(time.monotonic(), l) for l in lignes]
                if self.echo:
                    for l in lignes:
                        if _ECHO.fullmatch(l) and l not in self.sans_echo:
                            ecrivain.write(f"{l}\r".encode())
        except ConnectionError:
            pass
        self.fermetures += 1  # le client a fermé (lecture à vide)

    @property
    def commandes(self) -> list[str]:
        return [c for _, c in self.recues]

    async def pousser(self, brut: str):
        for e in self._clients:
            e.write(brut.encode())
            await e.drain()

    async def couper(self):
        for e in self._clients:
            e.close()
        self._clients.clear()

    async def arreter(self):
        await self.couper()
        self.serveur.close()
        await self.serveur.wait_closed()


@pytest_asyncio.fixture
async def faux_ampli():
    a = FauxAmpli()
    await a.demarrer()
    yield a
    await a.arreter()


async def _retirer_schema():
    """Le cœur ne connaît pas `plugin_denon`, et `clean_db` ne vide que ses
    tables à lui : chaque test repart d'un schéma neuf, retiré à la fin."""
    from backend.tests.conftest import test_engine

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS plugin_denon CASCADE"))


@pytest_asyncio.fixture
async def denon_installe(tmp_path, monkeypatch):
    """Le plugin copié et chargé par le vrai chargeur du cœur (sa migration
    jouée dans `plugin_denon`) ; l'appel rendu l'active."""
    from backend.config import settings
    from backend.main import app
    from backend.plugins import chargeur, etat

    await _retirer_schema()
    monkeypatch.setattr(settings, "plugins_dir", tmp_path)
    shutil.copytree(PLUGIN, tmp_path / "denon", ignore=shutil.ignore_patterns("tests", "__pycache__", "node_modules"))
    await chargeur.charger(app)

    async def activer():
        await chargeur.activer("denon")

    yield activer
    chargeur.arreter_tout()
    etat.vider()
    await _retirer_schema()


# ── le réveil ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def reveil(client, denon_installe):
    """Le plugin activé, avec un jeton."""
    from denon.tests.aides_reveil import JETON, regler

    await regler(client, jeton=JETON)
    await denon_installe()
    return client


@pytest_asyncio.fixture
async def table(denon_installe):
    """La table migrée, le plugin **inactif** : seul l'ordonnanceur du test
    tourne."""
    from backend.tests.conftest import test_session_factory

    return test_session_factory


# ── la séance ───────────────────────────────────────────────────────────


@pytest.fixture
def music_root(tmp_path, monkeypatch):
    from backend.config import settings

    racine = tmp_path / "music"
    racine.mkdir()
    monkeypatch.setattr(settings, "music_root", racine)
    return racine


@pytest_asyncio.fixture
async def dmr():
    from denon.tests.aides_seance import DmrAEtats

    d = DmrAEtats()
    await d.demarrer()
    yield d
    await d.arreter()


@pytest_asyncio.fixture
async def adresse(client):
    """`adresse_reseau` réglée par la route publique des réglages, puis vidée."""
    from denon.tests.aides import port_libre
    from denon.tests.aides_reveil import LOCAL
    from denon.tests.aides_seance import ip_locale

    hote = ip_locale() or "192.0.2.10"
    valeur = f"http://{hote}:{port_libre()}"
    r = await client.put("/api/settings/preferences", json={"adresse_reseau": valeur}, headers=LOCAL)
    assert r.status_code == 200, r.text
    yield valeur
    r = await client.put("/api/settings/preferences", json={"adresse_reseau": ""}, headers=LOCAL)
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def pistes(db_session, sample_data, music_root, tmp_path):
    """Six vraies pistes FLAC de 3 s, sur de vrais fichiers sous `music_root`.
    Assez courtes pour enchaîner vite, assez longues pour qu'une base lente
    (partagée par d'autres suites) ne fasse pas sauter une piste entière."""
    from backend.tests.bibliotheque_flux import piste

    fichier = tmp_path / "source.flac"
    fichier.write_bytes(b"fLaC" + bytes(64))
    album = sample_data["album1"]
    return [
        await piste(db_session, album, music_root, fichier, nom=f"{i:02}.flac", format="FLAC", sample_rate=44100,
                    bits_per_sample=16, duration_seconds=3.0, title_tag=f"Piste {i}")
        for i in range(1, 7)
    ]
