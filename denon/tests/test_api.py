"""L'API de denon-api, servie par l'écoute à part, de bout en bout :
HTTP réel → routeur → lien → faux ampli TCP.

La non-régression de Hublot y est double : ses appels rejoués à l'identique
(`test_appels_de_hublot`), puis son vrai client (`plugins/denon/plugin.js`)
exécuté par node contre cette API (`test_client_hublot_reel`).
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import socket
from pathlib import Path

import httpx
import pytest

from denon.backend import ecoute, routes
from denon.backend.lien import Config, Lien
from denon.backend.pilotes import PILOTES

from denon.tests.aides import attendre, port_libre

HUBLOT = Path(os.environ.get("HUBLOT_SRC", Path(__file__).resolve().parents[3] / "hublot"))
JETON = "secret-local"


@pytest.fixture
async def api(faux_ampli):
    """Une API branchée sur le faux ampli, servie seule sur un port libre."""
    reglages = {"jeton": JETON}
    lien = Lien(lambda: Config("127.0.0.1", faux_ampli.port, 0.01), PILOTES["avrx4000"], attente_min=0.05, attente_max=0.2)
    port = port_libre()
    taches = [
        asyncio.create_task(lien.tourner()),
        asyncio.create_task(ecoute.servir(routes.fabriquer(lien, lambda: reglages["jeton"]), port, logging.getLogger("t"), "127.0.0.1")),
    ]
    await attendre(lambda: lien.connecte and lien.en_attente == 0)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
        await attendre_http(client)
        client.headers["Authorization"] = f"Bearer {JETON}"
        yield client, faux_ampli, reglages, port
    for t in taches:
        t.cancel()
    await asyncio.gather(*taches, return_exceptions=True)


async def attendre_http(client):
    for _ in range(100):
        try:
            await client.get("/healthz")
            return
        except httpx.TransportError:
            await asyncio.sleep(0.02)
    raise AssertionError("l'écoute n'a pas démarré")


async def test_sante_sans_jeton(api):
    client, *_ = api
    r = await client.get("/healthz", headers={"Authorization": ""})
    assert r.json() == {"ok": True, "denon": True}


@pytest.mark.parametrize("auth", [None, "Bearer faux", JETON])
async def test_jeton_exige(api, auth):
    client, *_ = api
    entetes = {"Authorization": auth} if auth else {}
    client.headers.pop("Authorization")
    r = await client.get("/api/state", headers=entetes)
    assert (r.status_code, r.json()) == (401, {"error": "unauthorized"})


async def test_sans_jeton_regle_tout_est_ouvert(api):
    client, _, reglages, _ = api
    reglages["jeton"] = ""
    client.headers.pop("Authorization")
    assert (await client.get("/api/state")).status_code == 200


async def test_etat(api):
    client, ampli, *_ = api
    await ampli.pousser("PWON\rMV45\rMUOFF\rSIGAME\r")
    await asyncio.sleep(0.05)
    etat = (await client.get("/api/state")).json()
    assert {k: etat[k] for k in ("connected", "power", "volume", "mute", "source", "host", "port")} == {
        "connected": True, "power": True, "volume": -35, "mute": False, "source": "GAME", "host": "127.0.0.1", "port": ampli.port,
    }
    assert set(etat) == {"connected", "power", "volume", "mute", "source", "zone", "updatedAt", "host", "port"}


async def test_file(api):
    client, *_ = api
    assert (await client.get("/api/queue")).json() == {"pending": 0, "cadenceMs": 10}


@pytest.mark.parametrize("chemin, corps, commande", [
    ("/api/power", {"on": True}, "PWON"),
    ("/api/power", {"on": False}, "PWSTANDBY"),
    ("/api/power", None, "PWSTANDBY"),
    ("/api/mute", {"muted": True}, "MUON"),
    ("/api/source", {"source": "game"}, "SIGAME"),
    ("/api/volume", {"db": -35}, "MV450"),
    ("/api/volume", {"db": "-20.5"}, "MV595"),
    ("/api/volume/up", {}, "MVUP"),
    ("/api/volume/down", None, "MVDOWN"),
    ("/api/command", {"command": "SI?"}, "SI?"),
])
async def test_commandes(api, chemin, corps, commande):
    client, ampli, *_ = api
    r = await client.post(chemin, json=corps) if corps is not None else await client.post(chemin)
    assert (r.status_code, r.json()) == (200, {"accepted": True, "command": commande})
    await attendre(lambda: ampli.commandes[-1:] == [commande])


@pytest.mark.parametrize("chemin, corps, erreur", [
    ("/api/volume", {"db": None}, "invalid_volume"),
    ("/api/volume", {"db": "fort"}, "invalid_volume"),
    ("/api/volume", {"db": 18.5}, "invalid_volume"),
    ("/api/volume", {"db": True}, "invalid_volume"),
    ("/api/volume", {}, "invalid_volume"),
    ("/api/source", {"source": "SAT/CBL"}, "invalid_source"),
    ("/api/source", {}, "invalid_source"),
    ("/api/command", {}, "command_required"),
    ("/api/command", {"command": 12}, "command_required"),
])
async def test_refus_400(api, chemin, corps, erreur):
    client, *_ = api
    r = await client.post(chemin, json=corps)
    assert (r.status_code, r.json()) == (400, {"error": erreur})


async def test_commande_brute_invalide(api):
    client, *_ = api
    r = await client.post("/api/command", json={"command": "pwon"})
    assert (r.status_code, r.json()) == (503, {"error": "Commande Denon invalide"})


async def test_ampli_injoignable(api):
    client, ampli, *_ = api
    await ampli.arreter()
    for _ in range(50):
        if not (await client.get("/healthz")).json()["denon"]:
            break
        await asyncio.sleep(0.02)
    r = await client.post("/api/power", json={"on": True})
    assert r.status_code == 503
    assert r.json()["error"] == "denon_unreachable"


async def test_appels_de_hublot(api):
    """Les quatre gestes de la tuile Hublot, tels que son client les envoie."""
    client, ampli, *_ = api
    entetes = {"Authorization": f"Bearer {JETON}", "Content-Type": "application/json"}
    assert (await client.get("/api/state", headers={"Authorization": f"Bearer {JETON}"})).status_code == 200
    for chemin, corps in [("/api/power", {"on": True}), ("/api/mute", {"muted": False}), ("/api/volume/up", {}), ("/api/volume/down", {})]:
        r = await client.post(chemin, content=json.dumps(corps), headers=entetes)
        assert r.status_code == 200 and r.json()["accepted"] is True
    await attendre(lambda: ampli.commandes[-4:] == ["PWON", "MUOFF", "MVUP", "MVDOWN"])


@pytest.mark.skipif(not (shutil.which("node") and (HUBLOT / "plugins/denon/plugin.js").is_file()), reason="node ou le dépôt hublot absent (HUBLOT_SRC)")
async def test_client_hublot_reel(api):
    """Le vrai client Denon de Hublot, pointé sur l'écoute à part."""
    _, ampli, _, port = api
    await ampli.pousser("PWSTANDBY\rMV45\r")
    script = f"""
      const denon = (await import({json.dumps(str(HUBLOT / 'plugins/denon/plugin.js'))})).default;
      const config = {{ bridgeUrl: 'http://127.0.0.1:{port}/', token: {json.dumps(JETON)} }};
      const ctx = {{ fetch }};
      const avant = await denon.state(config, ctx);
      await denon.actions.power(config, ctx, {{ on: true }});
      await denon.actions.mute(config, ctx, {{ muted: true }});
      await denon.actions.volumeUp(config, ctx);
      await denon.actions.volumeDown(config, ctx);
      let refus = null;
      try {{ await denon.state({{ ...config, token: 'faux' }}, ctx); }} catch (e) {{ refus = e.message; }}
      console.log(JSON.stringify({{ avant, refus }}));
    """
    proc = await asyncio.create_subprocess_exec("node", "--input-type=module", "-e", script, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    sortie, erreurs = await asyncio.wait_for(proc.communicate(), 20)
    assert proc.returncode == 0, erreurs.decode()
    resultat = json.loads(sortie)
    assert resultat["avant"]["power"] is False and resultat["avant"]["volume"] == -35
    assert resultat["refus"] == "proxy Denon : HTTP 401"
    await attendre(lambda: ampli.commandes[-4:] == ["PWON", "MUON", "MVUP", "MVDOWN"])


# ── l'écoute à part ne met jamais unisson en danger ─────────────────────────


async def test_port_pris_journalise_sans_tomber(caplog):
    lien = Lien(lambda: Config("", 23, 0.01), PILOTES["avrx4000"])
    with socket.socket() as occupe:
        occupe.bind(("127.0.0.1", 0))
        occupe.listen()
        port = occupe.getsockname()[1]
        with caplog.at_level(logging.ERROR):
            await asyncio.wait_for(ecoute.servir(routes.fabriquer(lien, lambda: ""), port, logging.getLogger("t"), "127.0.0.1"), 2)
    assert "écoute à part impossible" in caplog.text


async def test_signaux_laisses_a_unisson_et_port_rendu(faux_ampli):
    avant = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    lien = Lien(lambda: Config("127.0.0.1", faux_ampli.port, 0.01), PILOTES["avrx4000"])
    port = port_libre()
    tache = asyncio.create_task(ecoute.servir(routes.fabriquer(lien, lambda: ""), port, logging.getLogger("t"), "127.0.0.1"))
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
        await attendre_http(client)
        assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == avant
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)
    assert tache.cancelled()
    ecoute.reserver(port, "127.0.0.1").close()  # le port est libéré


# ── constats de la relecture de la PR #5 ────────────────────────────────────


async def test_volume_entier_comme_denon_api(api):
    client, ampli, *_ = api
    await ampli.pousser("MV45\r")
    await asyncio.sleep(0.05)
    assert '"volume":-35,' in (await client.get("/api/state")).text


async def test_jeton_accentue_et_entete_non_ascii(api):
    client, _, reglages, _ = api
    reglages["jeton"] = "motdepassé"
    client.headers.pop("Authorization")
    bon = await client.get("/api/state", headers={"Authorization": "Bearer motdepassé".encode()})
    assert bon.status_code == 200
    faux = await client.get("/api/state", headers={"Authorization": "Bearer é".encode("latin-1")})
    assert (faux.status_code, faux.json()) == (401, {"error": "unauthorized"})


@pytest.mark.parametrize("contenu, type_, statut, code", [
    ("on=true", "application/x-www-form-urlencoded", 415, "unsupported_media_type"),
    ('{"on": tr', "application/json", 400, "invalid_json"),
])
async def test_corps_mal_forme_n_eteint_pas_l_ampli(api, contenu, type_, statut, code):
    client, ampli, *_ = api
    avant = list(ampli.commandes)
    r = await client.post("/api/power", content=contenu, headers={"Content-Type": type_})
    assert (r.status_code, r.json()) == (statut, {"error": code})
    await asyncio.sleep(0.05)
    assert ampli.commandes == avant


@pytest.mark.parametrize("corps, statut, commande", [
    ({"source": False}, 400, None),
    ({"source": 0}, 400, None),
    ({"on": []}, 200, "PWON"),
    ({"muted": {}}, 200, "MUON"),
])
async def test_verite_a_la_javascript(api, corps, statut, commande):
    client, *_ = api
    chemin = "/api/source" if "source" in corps else "/api/power" if "on" in corps else "/api/mute"
    r = await client.post(chemin, json=corps)
    assert r.status_code == statut
    if commande:
        assert r.json()["command"] == commande


async def test_port_hors_bornes_journalise_sans_tomber(caplog):
    lien = Lien(lambda: Config("", 23, 0.01), PILOTES["avrx4000"])
    with caplog.at_level(logging.ERROR):
        await asyncio.wait_for(ecoute.servir(routes.fabriquer(lien, lambda: ""), 81000, logging.getLogger("t"), "127.0.0.1"), 2)
    assert "écoute à part impossible" in caplog.text


async def test_loggers_d_unisson_intacts(faux_ampli):
    noms = ("uvicorn", "uvicorn.error", "uvicorn.access")
    photo = lambda: [(logging.getLogger(n).level, list(logging.getLogger(n).handlers), logging.getLogger(n).propagate) for n in noms]
    avant = photo()
    lien = Lien(lambda: Config("127.0.0.1", faux_ampli.port, 0.01), PILOTES["avrx4000"])
    port = port_libre()
    tache = asyncio.create_task(ecoute.servir(routes.fabriquer(lien, lambda: ""), port, logging.getLogger("t"), "127.0.0.1"))
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
        await attendre_http(client)
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)
    assert photo() == avant
