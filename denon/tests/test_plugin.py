"""Le plugin dans unisson, par le vrai chargeur : réglages, routes montées
sous `/api/plugins/denon/`, écoute à part, et arrêt propre à la désactivation."""

import asyncio
import socket

import httpx

from denon.tests.aides import attendre, port_libre

JETON = "jeton-de-test"
# Les routes /api/plugins exigent la même origine ; localhost passe toujours.
LOCAL = {"Host": "localhost", "Origin": "http://localhost"}


async def regler(client, **valeurs):
    r = await client.put("/api/plugins/denon/settings", json=valeurs, headers=LOCAL)
    assert r.status_code == 200, r.text


async def test_bascule_complete(client, faux_ampli, denon_installe):
    from backend.plugins import chargeur

    port = port_libre()
    await regler(client, hote="127.0.0.1", port_telnet=faux_ampli.port, cadence_ms=10, jeton=JETON, port_ecoute=port)
    await denon_installe()
    await attendre(lambda: faux_ampli.connexions == 1)

    auth = {"Authorization": f"Bearer {JETON}"}
    # Sous unisson.
    assert (await client.get("/api/plugins/denon/api/state")).status_code == 401
    await attendre(lambda: len(faux_ampli.commandes) == 4)
    r = await client.post("/api/plugins/denon/api/power", json={"on": True}, headers=auth)
    assert r.json() == {"accepted": True, "command": "PWON"}
    # Sur l'ancien port de denon-api, le même lien (une seule connexion).
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", headers=auth) as seul:
        for _ in range(100):
            try:
                etat = (await seul.get("/api/state")).json()
                break
            except httpx.TransportError:
                await asyncio.sleep(0.02)
        assert etat["connected"] is True and etat["port"] == faux_ampli.port
        assert (await seul.post("/api/volume/up")).json()["command"] == "MVUP"
    await attendre(lambda: faux_ampli.commandes[-2:] == ["PWON", "MVUP"])
    assert faux_ampli.connexions == 1
    # Le secret n'est jamais rendu.
    assert JETON not in (await client.get("/api/plugins/denon/settings", headers=LOCAL)).text

    await chargeur.desactiver("denon")
    await attendre(lambda: faux_ampli.fermetures == 1)
    assert (await client.get("/api/plugins/denon/healthz")).status_code == 404
    await attendre(lambda: _libre(port))  # le port est rendu


def _libre(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


async def test_pilote_inconnu_refuse_avec_son_motif(client, denon_installe):
    import pytest
    from backend.plugins import etat
    from backend.plugins.catalogues import Refus

    await regler(client, pilote="avr-inconnu")
    with pytest.raises(Refus, match="pilote Denon inconnu"):
        await denon_installe()
    assert not etat.en_marche("denon")
