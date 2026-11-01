"""Le pilote AVR-X4000 : les cas de `denon-api` (test/proxy.test.js), et plus."""

import pytest

from denon.backend.pilotes import PILOTES, lire_volume

P = PILOTES["avrx4000"]


def test_etat_lu_comme_denon_api():
    etat = {}
    for ligne in ("PWON", "MV595", "MUOFF", "SIGAME"):
        assert P.lire(etat, ligne)
    assert etat == {"power": True, "volume": -20.5, "mute": False, "source": "GAME"}


@pytest.mark.parametrize("brut, attendu", [("45", -35), ("595", -20.5), ("80", 0), ("00", -80), ("985", 18.5), ("UP", None), ("5", None), ("1234", None)])
def test_volume_aux_deux_formats(brut, attendu):
    assert lire_volume(brut) == attendu


@pytest.mark.parametrize("ligne", ["MVMAX 98", "MVUP", "ZMON", "SI", "", "PW"])
def test_trames_sans_effet(ligne):
    etat = {}
    assert not P.lire(etat, ligne)
    assert etat == {}


def test_veille_et_sourdine():
    etat = {}
    P.lire(etat, "PWSTANDBY")
    P.lire(etat, "MUON")
    assert etat == {"power": False, "mute": True}


@pytest.mark.parametrize("db, commande", [(-35, "MV450"), (-20.5, "MV595"), (-80, "MV000"), (18, "MV980"), (-20.25, "MV598"), (-20.75, "MV593")])
def test_encodage_du_volume(db, commande):
    assert P.volume(db) == commande


def test_gestes():
    assert (P.alimentation(True), P.alimentation(False)) == ("PWON", "PWSTANDBY")
    assert (P.sourdine(True), P.sourdine(False)) == ("MUON", "MUOFF")
    assert P.source("GAME") == "SIGAME"
    assert (P.volume_plus(), P.volume_moins()) == ("MVUP", "MVDOWN")


@pytest.mark.parametrize("commande, valide", [("PWON", True), ("MV?", True), ("SI SAT/CBL", False), ("pwon", False), ("", False), ("A" * 33, False), ("PW\rON", False), (None, False)])
def test_validation(commande, valide):
    assert P.valider(commande) is valide
