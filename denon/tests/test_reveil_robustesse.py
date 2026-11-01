"""Les cas limites du réveil relevés en relecture (PR #10) : fuseau invalide
réglé à chaud, identifiants hors d'un INTEGER, alarme de test orpheline,
modification au moment du départ, volumes exacts, testeur pendant l'heure
en double, ordonnanceurs concurrents et passage en échec.

Mêmes frontières que `test_reveil.py` : la vraie base, le vrai chargeur,
une horloge injectée."""

import asyncio
import logging
import time as chrono
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

from denon.backend import alarmes, reveil as routes_reveil
from denon.backend.ordonnanceur import Ordonnanceur
from denon.tests.aides_reveil import (
    AUTH, PARIS, RACINE, Horloge, a_paris, alarme, dans, lire_alarme, ordonnanceur, poser, regler, relire,
)

UTC = timezone.utc
TROP_GRAND = 2**31


# ── 1. un fuseau invalide réglé à chaud ─────────────────────────────────


# Un réglage vide revient au défaut (le cœur) : seuls ceux-ci sont invalides.
@pytest.mark.parametrize("invalide", ["Europe/paris", "Europe", "   "])
async def test_un_fuseau_invalide_a_chaud_ne_bloque_pas_le_reveil(reveil, invalide, caplog):
    caplog.set_level(logging.WARNING, logger="unisson.plugin.denon")
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(heure=dans(2), jours=127), headers=AUTH)
    ident = r.json()["id"]
    await regler(reveil, fuseau=invalide)

    debut = chrono.monotonic()
    while (a := await lire_alarme(reveil, ident))["dernier_resultat"] != "adresse_reseau_non_reglee":
        assert chrono.monotonic() - debut < 5, "le réveil est bloqué par le fuseau"
        await asyncio.sleep(0.05)

    h = (await reveil.get(f"{RACINE}/horloge", headers=AUTH)).json()
    assert h["fuseau"] == "Europe/Paris" and "fuseau inconnu" in h["avertissement"]
    liste = (await reveil.get(f"{RACINE}/alarmes", headers=AUTH)).json()
    assert liste["avertissement"] == h["avertissement"]
    # Journalisé une fois, pas à chaque tour.
    assert caplog.text.count("réglage fuseau") == 1

    await regler(reveil, fuseau="Asia/Tokyo")
    h = (await reveil.get(f"{RACINE}/horloge", headers=AUTH)).json()
    assert (h["fuseau"], h["avertissement"]) == ("Asia/Tokyo", None)


# ── 2. les identifiants hors d'un INTEGER ───────────────────────────────


async def test_les_identifiants_trop_grands_sont_refuses(reveil):
    for champs, champ in (
        ({"contexte": "artiste", "contexte_id": TROP_GRAND}, "contexte_id"),
        ({"genre_id": TROP_GRAND}, "genre_id"),
    ):
        r = await reveil.post(f"{RACINE}/alarmes", json=alarme(**champs), headers=AUTH)
        assert r.status_code == 422, r.text
        assert [e["champ"] for e in r.json()["erreurs"]] == [champ]
    r = await reveil.post(f"{RACINE}/tester", json={"dans_s": 5, "alarme_id": TROP_GRAND}, headers=AUTH)
    assert r.status_code == 422
    for methode, chemin in (("PUT", "/alarmes"), ("DELETE", "/alarmes"), ("GET", "/tester")):
        r = await reveil.request(methode, f"{RACINE}{chemin}/{TROP_GRAND}", json={}, headers=AUTH)
        assert r.status_code == 422, (methode, chemin, r.text)


# ── 3. l'alarme de test orpheline ───────────────────────────────────────


async def test_l_alarme_de_test_prise_puis_orpheline_reste_lisible_puis_part(table):
    horloge = Horloge(a_paris("2026-11-06T06:59:50"))
    async with table() as s:
        test = await alarmes.creer(s, alarmes.valider(alarme(nom="Test 07:00:00", jours=0)), horloge(), test=True)
        await s.commit()
    # unisson s'arrête juste après `prendre`, avant la suppression.
    horloge.t = a_paris("2026-11-06T07:00:00.300")
    async with table() as s:
        prise = await alarmes.prendre(s, test["id"], a_paris("2026-11-06T07:00"), lu=test["arme_le"],
                                      execution=horloge(), resultat="en_cours")
        await s.commit()
    assert prise is not None

    o = ordonnanceur(table, horloge)
    res = await o.resultat_test(test["id"])
    assert (res["etat"], res["retard_ms"], res["dernier_resultat"]) == ("partie", 300, "en_cours")

    # Au démarrage, l'ordonnanceur la supprime.
    tache = asyncio.create_task(o.tourner())
    try:
        debut = chrono.monotonic()
        while await relire(table, test["id"]) is not None:
            assert chrono.monotonic() - debut < 3
            await asyncio.sleep(0.02)
    finally:
        tache.cancel()
        await asyncio.gather(tache, return_exceptions=True)


async def test_un_resultat_trop_long_est_tronque_et_le_test_supprime(table):
    horloge = Horloge(a_paris("2026-11-06T06:59:50"))
    async with table() as s:
        test = await alarmes.creer(s, alarmes.valider(alarme(nom="Test", jours=0)), horloge(), test=True)
        await s.commit()

    async def bavarde(_):
        return "x" * 60

    horloge.t = a_paris("2026-11-06T07:00:00.100")
    o = Ordonnanceur(table, lambda: PARIS, declencher=bavarde, maintenant=horloge)
    await o.passer()
    assert await relire(table, test["id"]) is None
    assert o.tests[test["id"]]["dernier_resultat"] == "x" * 40


# ── 4. une modification au moment du départ ─────────────────────────────


async def test_un_renommage_juste_apres_l_heure_ne_fait_pas_sauter_l_alarme(table):
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    a = await poser(table, horloge)
    horloge.t = a_paris("2026-11-06T07:00:00.200")
    async with table() as s:
        await alarmes.modifier(s, a["id"], {**alarmes.valider({"nom": "Renommée"}, a)}, horloge(), a)
        await s.commit()
    horloge.t = a_paris("2026-11-06T07:00:00.500")
    await ordonnanceur(table, horloge, appels).passer()
    assert [i for i, _ in appels] == [a["id"]]


async def test_une_heure_changee_juste_avant_part_a_la_nouvelle(table):
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    a = await poser(table, horloge)
    horloge.t = a_paris("2026-11-06T06:59:59")
    async with table() as s:
        await alarmes.modifier(s, a["id"], alarmes.valider({"heure": "08:00"}, a), horloge(), a)
        await s.commit()
    o = ordonnanceur(table, horloge, appels)
    horloge.t = a_paris("2026-11-06T07:00:01")
    assert await o.passer() == a_paris("2026-11-06T08:00")
    assert appels == []
    horloge.t = a_paris("2026-11-06T08:00:00.100")
    await o.passer()
    assert [i for i, _ in appels] == [a["id"]]


async def test_une_heure_changee_entre_la_lecture_et_le_depart_ne_part_pas(table):
    horloge = Horloge(a_paris("2026-11-05T22:00"))
    a = await poser(table, horloge)
    # L'ordonnanceur a lu l'alarme de 07:00 ; un PUT la passe à 08:00 juste
    # avant qu'il ne la prenne.
    horloge.t = a_paris("2026-11-06T07:00:00.200")
    async with table() as s:
        lue = await alarmes.lire(s, a["id"])
        await alarmes.modifier(s, a["id"], alarmes.valider({"heure": "08:00"}, lue), horloge(), lue)
        await s.commit()
    async with table() as s:
        prise = await alarmes.prendre(s, a["id"], a_paris("2026-11-06T07:00"), lu=lue["arme_le"],
                                      execution=horloge(), resultat="en_cours")
        await s.commit()
    assert prise is None
    assert (await relire(table, a["id"]))["derniere_execution"] is None


# ── 5. les volumes exacts ───────────────────────────────────────────────


async def test_les_volumes_reviennent_tels_quels(reveil):
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(volume_depart_db=-35.3, volume_cible_db=-12.7), headers=AUTH)
    assert (r.json()["volume_depart_db"], r.json()["volume_cible_db"]) == (-35.3, -12.7)
    lue = await lire_alarme(reveil, r.json()["id"])
    assert (lue["volume_depart_db"], lue["volume_cible_db"]) == (-35.3, -12.7)


# ── 6. le testeur pendant l'heure en double ─────────────────────────────


async def test_le_testeur_pendant_l_heure_en_double(table):
    # Dimanche 25 octobre 2026 : 02:00 à 03:00 se passe deux fois à Paris.
    horloge = Horloge(datetime(2026, 10, 25, 0, 30, 10, tzinfo=UTC))  # 02:30:10+02:00
    o = Ordonnanceur(table, lambda: PARIS, maintenant=horloge)
    app = FastAPI()
    fuseau = alarmes.FuseauRegle(lambda: "Europe/Paris", logging.getLogger("test"))
    app.include_router(routes_reveil.fabriquer(o, table, fuseau))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        # Premier passage : l'heure locale désigne bien l'échéance.
        r = await c.post("/reveil/tester", json={"dans_s": 5})
        assert r.status_code == 201, r.text
        assert r.json()["echeance"] == "2026-10-25T02:30:15.000+02:00" == r.json()["alarme"]["prochaine"]
        # Second passage (02:30:10+01:00) : « 02:30:15 » serait le premier,
        # déjà passé ; l'alarme partirait le lendemain. Refus motivé.
        horloge.t = datetime(2026, 10, 25, 1, 30, 10, tzinfo=UTC)
        r = await c.post("/reveil/tester", json={"dans_s": 5})
        assert r.status_code == 422, r.text
        assert "existe deux fois" in r.json()["erreurs"][0]["message"]


# ── 7. ordonnanceurs concurrents, passage en échec ──────────────────────


async def test_deux_ordonnanceurs_en_parallele_un_seul_depart(table):
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    await poser(table, horloge)
    horloge.t = a_paris("2026-11-06T07:00:00.100")
    await asyncio.gather(*(ordonnanceur(table, horloge, appels).passer() for _ in range(2)))
    assert len(appels) == 1


async def test_tourner_survit_a_un_passage_en_echec(table):
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    await poser(table, horloge)
    horloge.t = a_paris("2026-11-06T07:00:00.100")
    ratees = []

    def session_capricieuse():
        # La base ne répond pas la première fois.
        if not ratees:
            ratees.append(1)
            raise ConnectionError("base indisponible")
        return table()

    o = ordonnanceur(session_capricieuse, horloge, appels)
    tache = asyncio.create_task(o.tourner())
    try:
        debut = chrono.monotonic()
        while not appels:
            assert chrono.monotonic() - debut < 3, "l'ordonnanceur n'a pas repris"
            assert not tache.done(), tache
            await asyncio.sleep(0.02)
    finally:
        tache.cancel()
        await asyncio.gather(tache, return_exceptions=True)
    assert ratees == [1] and len(appels) == 1
