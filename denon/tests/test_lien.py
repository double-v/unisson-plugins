"""Le lien telnet contre un faux ampli TCP : connexion unique, file, cadence,
reconnexion, arrêt."""

import asyncio
import socket

import pytest

from denon.backend.lien import Config, Injoignable, Lien
from denon.backend.pilotes import PILOTES

from denon.tests.aides import attendre

CADENCE = 0.05


def lien_vers(ampli, **k) -> Lien:
    cfg = k.pop("config", None) or (lambda: Config("127.0.0.1", ampli.port, CADENCE))
    return Lien(cfg, PILOTES["avrx4000"], attente_min=0.05, attente_max=0.2, **k)


@pytest.fixture
async def lance(faux_ampli):
    taches = []

    async def lancer(lien):
        taches.append(asyncio.create_task(lien.tourner()))
        await attendre(lambda: lien.connecte and lien.en_attente == 0)
        return lien

    yield lancer
    for t in taches:
        t.cancel()
    await asyncio.gather(*taches, return_exceptions=True)


async def test_requetes_initiales_a_la_cadence(faux_ampli, lance):
    await lance(lien_vers(faux_ampli))
    await attendre(lambda: len(faux_ampli.recues) == 4)
    assert faux_ampli.commandes == ["PW?", "MV?", "MU?", "SI?"]
    instants = [t for t, _ in faux_ampli.recues]
    assert all(b - a >= CADENCE * 0.9 for a, b in zip(instants, instants[1:]))


async def test_etat_pousse_par_l_ampli_meme_en_morceaux(faux_ampli, lance):
    lien = await lance(lien_vers(faux_ampli))
    await faux_ampli.pousser("PW")
    await faux_ampli.pousser("ON\rMV45\rMUOFF\rSIGAME\rZMON\r")
    await attendre(lambda: lien.etat["source"] == "GAME")
    assert {k: lien.etat[k] for k in ("connected", "power", "volume", "mute")} == {"connected": True, "power": True, "volume": -35, "mute": False}
    assert lien.etat["updatedAt"].endswith("Z")


async def test_commande_envoyee_apres_les_precedentes(faux_ampli, lance):
    lien = await lance(lien_vers(faux_ampli))
    await asyncio.gather(lien.envoyer("MVUP"), lien.envoyer("MVDOWN"))
    assert faux_ampli.commandes[-2:] == ["MVUP", "MVDOWN"]


async def test_commande_invalide_refusee_avant_la_file(faux_ampli, lance):
    lien = await lance(lien_vers(faux_ampli))
    with pytest.raises(ValueError):
        await lien.envoyer("PW\rON")
    assert lien.en_attente == 0


async def test_injoignable_refuse_sans_garder_la_commande(faux_ampli):
    await faux_ampli.arreter()
    lien = lien_vers(faux_ampli)
    tache = asyncio.create_task(lien.tourner())
    try:
        with pytest.raises(Injoignable):
            await asyncio.wait_for(lien.envoyer("PWON"), 1)
        assert lien.en_attente == 0
    finally:
        tache.cancel()
        await asyncio.gather(tache, return_exceptions=True)


async def test_reconnexion_apres_coupure(faux_ampli, lance):
    lien = await lance(lien_vers(faux_ampli))
    await faux_ampli.couper()
    await attendre(lambda: not lien.connecte)
    assert lien.etat["connected"] is False
    await attendre(lambda: faux_ampli.connexions == 2 and lien.connecte)
    await lien.envoyer("PWON")
    await attendre(lambda: "PWON" in faux_ampli.commandes)


async def test_hote_relu_a_la_reconnexion(faux_ampli):
    """Changer l'hôte dans les réglages prend effet sans redémarrer."""
    cfg = {"c": Config("", 23, CADENCE)}
    lien = lien_vers(faux_ampli, config=lambda: cfg["c"])
    tache = asyncio.create_task(lien.tourner())
    try:
        await asyncio.sleep(0.1)
        assert faux_ampli.connexions == 0
        cfg["c"] = Config("127.0.0.1", faux_ampli.port, CADENCE)
        await attendre(lambda: lien.connecte, 1)
    finally:
        tache.cancel()
        await asyncio.gather(tache, return_exceptions=True)


async def test_arret_ferme_la_socket_et_refuse_la_file(faux_ampli):
    lien = lien_vers(faux_ampli, config=lambda: Config("127.0.0.1", faux_ampli.port, 1.0))
    tache = asyncio.create_task(lien.tourner())
    await attendre(lambda: lien.connecte)
    en_file = asyncio.create_task(lien.envoyer("PWON"))  # derrière 4 requêtes à 1 s
    await asyncio.sleep(0.05)
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)
    with pytest.raises(Injoignable, match="arrêté"):
        await en_file
    assert not lien.connecte
    await attendre(lambda: faux_ampli.fermetures == 1)


# ── constats de la relecture de la PR #5 ────────────────────────────────────


async def test_des_milliers_d_echecs_ne_tuent_pas_le_lien():
    """2**1024 débordait : une nuit d'ampli éteint mettait le plugin en panne."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        ferme = s.getsockname()[1]  # lié, jamais à l'écoute : connexion refusée
        lien = Lien(lambda: Config("127.0.0.1", ferme, 0.0), PILOTES["avrx4000"], attente_min=1e-9, attente_max=1e-9)
        tache = asyncio.create_task(lien.tourner())
        await asyncio.sleep(1.5)
        assert not tache.done(), tache.exception() if tache.done() else None
        tache.cancel()
        await asyncio.gather(tache, return_exceptions=True)


@pytest.mark.parametrize("hote, port", [("127.0.0.1", 81000), ("a..b", 23)])
async def test_configuration_fausse_reessayee_sans_tomber(hote, port):
    lien = Lien(lambda: Config(hote, port, 0.0), PILOTES["avrx4000"], attente_min=0.01, attente_max=0.01)
    tache = asyncio.create_task(lien.tourner())
    await asyncio.sleep(0.2)
    assert not tache.done()
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)


async def test_envoyer_apres_l_arret_refuse_au_lieu_de_pendre(faux_ampli):
    lien = lien_vers(faux_ampli)
    tache = asyncio.create_task(lien.tourner())
    await attendre(lambda: lien.connecte)
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)
    with pytest.raises(Injoignable, match="arrêté"):
        await asyncio.wait_for(lien.envoyer("PWON"), 1)
