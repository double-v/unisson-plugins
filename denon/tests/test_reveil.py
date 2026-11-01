"""Les alarmes du réveil, par le vrai chargeur et la vraie base de test :
migration dans `plugin_denon`, validation, routes, ordonnanceur et testeur
de fuseau.

Les faux restent à la frontière : l'horloge est injectée dans
l'ordonnanceur, rien d'autre. Les tests « en temps réel » (réveil par une
écriture, testeur de 5 s) passent par le plugin activé, sans horloge
injectée.
"""

import asyncio
import logging
import time as chrono
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from denon.backend import alarmes
from denon.backend.ordonnanceur import Ordonnanceur
from denon.tests.aides import attendre
from denon.tests.aides_reveil import (
    AUTH, PARIS, RACINE, UTC, Horloge, a_paris, alarme, dans, lire_alarme, ordonnanceur, poser, regler, relire,
)


# ── la migration ────────────────────────────────────────────────────────


async def test_la_migration_cree_la_table_dans_son_schema(denon_installe, db_session):
    tables = await db_session.execute(
        text("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('alarmes', 'alembic_version_denon')")
    )
    assert sorted(tables.all()) == [("plugin_denon", "alarmes"), ("plugin_denon", "alembic_version_denon")]


# ── la validation ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("champs", "champ"),
    [
        ({"heure": "7:00"}, "heure"),
        ({"heure": "24:00"}, "heure"),
        ({"heure": "07:60"}, "heure"),
        ({"heure": "07:00:60"}, "heure"),
        ({"jours": 128}, "jours"),
        ({"jours": -1}, "jours"),
        ({"jours": True}, "jours"),
        ({"contexte": "radio"}, "contexte"),
        ({"contexte": "playlist"}, "contexte_id"),
        ({"contexte": "artiste", "contexte_id": 0}, "contexte_id"),
        ({"contexte_id": 3}, "contexte_id"),
        ({"melange": True}, "melange"),
        ({"contexte": "playlist", "contexte_id": 1, "genre_id": 1}, "genre_id"),
        ({"contexte": "album", "contexte_id": 1, "favoris": True}, "favoris"),
        ({"contexte": "album", "contexte_id": 1, "format": "FLAC"}, "format"),
        ({"format": "fl ac"}, "format"),
        ({"volume_depart_db": -81}, "volume_depart_db"),
        ({"volume_cible_db": 18.5}, "volume_cible_db"),
        ({"volume_cible_db": "-30"}, "volume_cible_db"),
        ({"montee_s": -1}, "montee_s"),
        ({"montee_s": 1.5}, "montee_s"),
        ({"montee_s": 3601}, "montee_s"),  # plafond : 1 h
        ({"fin_mode": "jamais"}, "fin_mode"),
        ({"fin_mode": "duree", "fin_valeur": 0}, "fin_valeur"),
        ({"fin_mode": "pistes", "fin_valeur": None}, "fin_valeur"),
        ({"fin_mode": "sans_limite", "fin_valeur": 3}, "fin_valeur"),
        ({"nom": "  "}, "nom"),
        ({"active": "oui"}, "active"),
        ({"derniere_execution": "2026-11-01"}, "derniere_execution"),
    ],
)
async def test_refus_motives(reveil, champs, champ):
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(**champs), headers=AUTH)
    assert r.status_code == 422, r.text
    corps = r.json()
    assert corps["error"] == "alarme_invalide"
    assert champ in [e["champ"] for e in corps["erreurs"]], corps
    assert all(e["message"] for e in corps["erreurs"])


async def test_tous_les_motifs_d_un_coup(reveil):
    r = await reveil.post(f"{RACINE}/alarmes", json={"heure": "25:00", "fin_mode": "x"}, headers=AUTH)
    assert r.status_code == 422
    assert {e["champ"] for e in r.json()["erreurs"]} == {"nom", "heure", "fin_mode"}


async def test_le_contexte_doit_exister(reveil, sample_data, db_session):
    artiste, album, genre = sample_data["artist"].id, sample_data["album1"].id, sample_data["genre"].id
    playlist = (await db_session.execute(
        text("INSERT INTO playlists (name, created_at, updated_at) VALUES ('Matin', 'x', 'x') RETURNING id")
    )).scalar_one()
    await db_session.commit()

    for champs in (
        {"contexte": "playlist", "contexte_id": playlist, "melange": True},
        {"contexte": "artiste", "contexte_id": artiste},
        {"contexte": "album", "contexte_id": album},
        {"genre_id": genre, "format": "flac", "favoris": True},
    ):
        r = await reveil.post(f"{RACINE}/alarmes", json=alarme(**champs), headers=AUTH)
        assert r.status_code == 201, r.text
    assert r.json()["format"] == "FLAC"

    for champs, motif in (
        ({"contexte": "playlist", "contexte_id": playlist + 99}, "playlist"),
        ({"contexte": "artiste", "contexte_id": artiste + 99}, "artiste"),
        ({"contexte": "album", "contexte_id": album + 99}, "album"),
        ({"genre_id": genre + 99}, "genre"),
    ):
        r = await reveil.post(f"{RACINE}/alarmes", json=alarme(**champs), headers=AUTH)
        assert r.status_code == 422, r.text
        assert motif in r.json()["erreurs"][0]["message"]

    # Un album à la corbeille ne se joue plus.
    await db_session.execute(text("UPDATE albums SET trashed = 1 WHERE id = :id"), {"id": album})
    await db_session.commit()
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(contexte="album", contexte_id=album), headers=AUTH)
    assert r.status_code == 422


# ── les routes ──────────────────────────────────────────────────────────


async def test_le_jeton_est_exige(reveil):
    for methode, chemin in (
        ("GET", "/alarmes"), ("POST", "/alarmes"), ("PUT", "/alarmes/1"), ("DELETE", "/alarmes/1"),
        ("POST", "/tester"), ("GET", "/tester/1"), ("GET", "/horloge"),
    ):
        r = await reveil.request(methode, RACINE + chemin, json={})
        assert r.status_code == 401, (methode, chemin)
        assert r.json() == {"error": "unauthorized"}
        r = await reveil.request(methode, RACINE + chemin, json={}, headers={"Authorization": "Bearer faux"})
        assert r.status_code == 401


async def test_creer_lister_modifier_supprimer(reveil):
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(heure="06:45:30", volume_depart_db=-60, montee_s=3600), headers=AUTH)
    assert r.status_code == 201, r.text
    cree = r.json()
    assert cree["heure"] == "06:45:30" and cree["active"] is True and cree["test"] is False
    assert cree["fin_mode"] == "duree" and cree["fin_valeur"] == 60
    # La prochaine occurrence, dans le fuseau, avec son décalage.
    prochaine = datetime.fromisoformat(cree["prochaine"])
    assert prochaine > datetime.now(UTC) and prochaine.strftime("%H:%M:%S") == "06:45:30"
    assert prochaine.utcoffset() == prochaine.astimezone(PARIS).utcoffset()

    liste = (await reveil.get(f"{RACINE}/alarmes", headers=AUTH)).json()
    assert liste["fuseau"] == "Europe/Paris" and [a["id"] for a in liste["alarmes"]] == [cree["id"]]

    # Un PUT ne change que ce qu'il donne ; il revalide l'ensemble.
    r = await reveil.put(f"{RACINE}/alarmes/{cree['id']}", json={"active": False, "heure": "07:00:00"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["heure"] == "07:00" and r.json()["prochaine"] is None and r.json()["volume_depart_db"] == -60
    r = await reveil.put(f"{RACINE}/alarmes/{cree['id']}", json={"fin_mode": "sans_limite"}, headers=AUTH)
    assert r.status_code == 422  # fin_valeur reste 60
    r = await reveil.put(f"{RACINE}/alarmes/{cree['id']}", json={"fin_mode": "sans_limite", "fin_valeur": None}, headers=AUTH)
    assert r.status_code == 200

    assert (await reveil.put(f"{RACINE}/alarmes/999999", json={}, headers=AUTH)).status_code == 404
    assert (await reveil.delete(f"{RACINE}/alarmes/{cree['id']}", headers=AUTH)).status_code == 204
    assert (await reveil.delete(f"{RACINE}/alarmes/{cree['id']}", headers=AUTH)).status_code == 404
    assert (await reveil.get(f"{RACINE}/alarmes", headers=AUTH)).json()["alarmes"] == []


async def test_horloge(reveil):
    h = (await reveil.get(f"{RACINE}/horloge", headers=AUTH)).json()
    local, utc = datetime.fromisoformat(h["local"]), datetime.fromisoformat(h["utc"])
    assert h["fuseau"] == "Europe/Paris" and h["utc"].endswith("Z")
    assert abs((local - utc).total_seconds()) < 1
    assert h["decalage"] == local.strftime("%z")[:3] + ":" + local.strftime("%z")[3:]
    assert abs((utc - datetime.now(UTC)).total_seconds()) < 2

    await regler(reveil, fuseau="Asia/Tokyo")
    h = (await reveil.get(f"{RACINE}/horloge", headers=AUTH)).json()
    assert (h["fuseau"], h["decalage"]) == ("Asia/Tokyo", "+09:00")


async def test_un_fuseau_inconnu_refuse_l_activation(client, denon_installe):
    from backend.plugins.catalogues import Refus

    await regler(client, fuseau="Mars/Olympus")
    with pytest.raises(Refus, match="fuseau inconnu"):
        await denon_installe()


# ── l'ordonnanceur, horloge injectée ────────────────────────────────────


async def test_part_a_l_heure_une_seule_fois(table):
    # Jeudi 5 novembre 2026, 22:00 : on arme l'alarme de semaine de 07:00.
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    a = await poser(table, horloge)
    o = ordonnanceur(table, horloge, appels)
    assert await o.passer() == a_paris("2026-11-06T07:00")
    assert appels == []

    horloge.t = a_paris("2026-11-06T07:00:00.250")
    await o.passer()
    assert appels == [(a["id"], horloge.t)]
    lue = await relire(table, a["id"])
    assert lue["dernier_resultat"] == "declenchee" and lue["active"] is True
    assert alarmes.retard_ms(lue) == 250
    # Ni un second passage, ni un ordonnanceur neuf (un redémarrage) ne la
    # refont partir dans la fenêtre de rattrapage.
    horloge.t += timedelta(minutes=2)
    await o.passer()
    await ordonnanceur(table, horloge, appels).passer()
    assert len(appels) == 1
    # La suivante : lundi (le week-end est sauté).
    assert alarmes.vue(lue, PARIS, horloge())["prochaine"] == "2026-11-09T07:00:00.000+01:00"


async def test_rattrapage_puis_manquee(table):
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    en_retard = await poser(table, horloge, nom="En retard")
    trop_tard = await poser(table, horloge, nom="Trop tard", heure="06:40")
    # unisson était arrêté et repart à 07:08 : la première (07:00) a 8 min
    # de retard, elle part ; la seconde (06:40) en a 28, elle est manquée.
    horloge.t = a_paris("2026-11-06T07:08")
    await ordonnanceur(table, horloge, appels).passer()
    assert appels == [(en_retard["id"], horloge.t)]
    assert alarmes.retard_ms(await relire(table, en_retard["id"])) == 8 * 60 * 1000
    manquee = await relire(table, trop_tard["id"])
    assert manquee["dernier_resultat"] == "manquee" and manquee["derniere_execution"] is None
    assert manquee["active"] is True  # une alarme répétée reste armée
    # Manquée une fois, elle ne part pas plus tard non plus.
    horloge.t += timedelta(seconds=30)
    await ordonnanceur(table, horloge, appels).passer()
    assert len(appels) == 1


async def test_l_alarme_unique_se_desactive_apres_son_passage(table):
    horloge, appels = Horloge(a_paris("2026-11-05T22:00")), []
    unique = await poser(table, horloge, jours=0)
    manquee = await poser(table, horloge, jours=0, heure="06:00")
    horloge.t = a_paris("2026-11-06T07:00:01")
    o = ordonnanceur(table, horloge, appels)
    assert await o.passer() is not None
    assert appels == [(unique["id"], horloge.t)]
    for ident, resultat in ((unique["id"], "declenchee"), (manquee["id"], "manquee")):
        lue = await relire(table, ident)
        assert (lue["active"], lue["dernier_resultat"]) == (False, resultat)
        assert alarmes.vue(lue, PARIS, horloge())["prochaine"] is None
    # Plus rien à attendre : il dormira 30 s.
    assert await o.passer() is None


async def test_l_accroche_qui_echoue_est_notee(table):
    horloge = Horloge(a_paris("2026-11-05T22:00"))
    a = await poser(table, horloge)

    async def casse(_):
        raise RuntimeError("ampli")

    horloge.t = a_paris("2026-11-06T07:00")
    await Ordonnanceur(table, lambda: PARIS, declencher=casse, maintenant=horloge).passer()
    assert (await relire(table, a["id"]))["dernier_resultat"] == "erreur:RuntimeError"


# ── en temps réel, par le plugin activé ─────────────────────────────────


async def test_une_ecriture_reveille_l_ordonnanceur(reveil):
    # Sans alarme, il dort 30 s ; l'alarme créée part quand même à l'heure.
    await asyncio.sleep(0.3)
    heure = dans(2)
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(heure=heure, jours=127), headers=AUTH)
    ident = r.json()["id"]
    debut = chrono.monotonic()
    # Le départ est noté (`en_cours`) avant l'accroche, son résultat après.
    while (a := await lire_alarme(reveil, ident))["dernier_resultat"] != "declenchee":
        assert chrono.monotonic() - debut < 5, "l'ordonnanceur ne s'est pas réveillé"
        await asyncio.sleep(0.05)
    assert a["derniere_execution"] is not None and a["dernier_retard_ms"] < 1000


async def test_pas_de_double_depart_apres_une_reactivation(reveil, caplog):
    from backend.plugins import chargeur

    caplog.set_level(logging.INFO, logger="unisson.plugin.denon")
    r = await reveil.post(f"{RACINE}/alarmes", json=alarme(heure=dans(1.5), jours=127), headers=AUTH)
    ident = r.json()["id"]
    await attendre(lambda: "déclenchée" in caplog.text, delai=4)
    avant = await lire_alarme(reveil, ident)

    # Réactivé dans la fenêtre de rattrapage : l'alarme ne repart pas.
    await chargeur.desactiver("denon")
    await chargeur.activer("denon")
    await asyncio.sleep(1)
    assert caplog.text.count("déclenchée") == 1
    assert (await lire_alarme(reveil, ident))["derniere_execution"] == avant["derniere_execution"]


async def test_le_testeur_part_dans_cinq_secondes(reveil):
    debut = chrono.monotonic()
    r = await reveil.post(f"{RACINE}/tester", json={"dans_s": 5}, headers=AUTH)
    assert r.status_code == 201, r.text
    corps = r.json()
    test = corps["alarme"]
    assert test["test"] is True and test["jours"] == 0 and test["nom"] == f"Test {test['heure']}"
    assert (test["contexte"], test["fin_mode"], test["fin_valeur"]) == ("bibliotheque", "pistes", 1)
    # L'heure du serveur dans le fuseau, avec son décalage, l'UTC, l'échéance.
    h = corps["horloge"]
    assert h["fuseau"] == "Europe/Paris" and h["decalage"] in ("+01:00", "+02:00") and h["utc"].endswith("Z")
    echeance = datetime.fromisoformat(corps["echeance"])
    assert 5 <= (echeance - datetime.fromisoformat(h["utc"])).total_seconds() <= 6
    assert echeance == datetime.fromisoformat(corps["echeance_utc"])
    assert corps["echeance"] == test["prochaine"]
    assert (await reveil.get(f"{RACINE}/tester/{test['id']}", headers=AUTH)).json()["etat"] == "en_attente"

    while (res := (await reveil.get(f"{RACINE}/tester/{test['id']}", headers=AUTH)).json())["etat"] == "en_attente":
        assert chrono.monotonic() - debut < 9
        await asyncio.sleep(0.02)
    ecoule = chrono.monotonic() - debut
    # Échéance arrondie à la seconde suivante (5 à 6 s), puis jusqu'à 1 s de
    # retard toléré : la précision elle-même se juge sur `retard_ms`.
    assert 5 <= ecoule <= 7.5, ecoule
    assert res["etat"] == "partie" and res["dernier_resultat"] == "declenchee"
    assert res["echeance"] == corps["echeance"]
    assert 0 <= res["retard_ms"] < 1000
    ecart = datetime.fromisoformat(res["depart"]) - echeance  # rendus à la milliseconde près
    assert abs(ecart.total_seconds() * 1000 - res["retard_ms"]) <= 1
    # Partie, elle s'est supprimée ; son résultat reste lisible.
    assert (await reveil.get(f"{RACINE}/alarmes", headers=AUTH)).json()["alarmes"] == []
    assert (await reveil.get(f"{RACINE}/tester/{test['id']}", headers=AUTH)).json() == res


async def test_le_testeur_reprend_l_alarme_choisie(reveil, sample_data):
    artiste = sample_data["artist"].id
    await reveil.post(f"{RACINE}/alarmes", json=alarme(volume_cible_db=-20, montee_s=60), headers=AUTH)
    choisie = (await reveil.post(
        f"{RACINE}/alarmes", json=alarme(contexte="artiste", contexte_id=artiste, fin_mode="sans_limite", fin_valeur=None),
        headers=AUTH,
    )).json()

    test = (await reveil.post(f"{RACINE}/tester", json={"dans_s": 10}, headers=AUTH)).json()["alarme"]
    assert (test["volume_cible_db"], test["montee_s"], test["contexte"]) == (-20, 60, "bibliotheque")
    test = (await reveil.post(f"{RACINE}/tester", json={"dans_s": 10, "alarme_id": choisie["id"]}, headers=AUTH)).json()["alarme"]
    assert (test["contexte"], test["contexte_id"], test["fin_mode"], test["fin_valeur"]) == ("artiste", artiste, "pistes", 1)

    for corps in ({"dans_s": 7}, {}, {"dans_s": True}, {"dans_s": 5, "alarme_id": "1"}):
        r = await reveil.post(f"{RACINE}/tester", json=corps, headers=AUTH)
        assert r.status_code == 422, corps
    assert (await reveil.post(f"{RACINE}/tester", json={"dans_s": 5, "alarme_id": 999999}, headers=AUTH)).status_code == 404
    assert (await reveil.get(f"{RACINE}/tester/999999", headers=AUTH)).status_code == 404
