"""ntfy, par le vrai chargeur, contre un vrai serveur HTTP qui joue ntfy.

Le cœur pose les événements au fil et sa boucle (`fil.tick`) décide quand le
canal parle ; on vérifie ce qui arrive **chez ntfy** : le sujet, le titre, la
priorité, le jeton, le lien profond vers le fil.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ntfy.tests.aides import ENTETES, ID, FauxNtfy, port_ferme

REGLAGES = f"/api/plugins/{ID}/settings"


def _local(*a) -> datetime:
    return datetime(*a, tzinfo=ZoneInfo("Europe/Paris"))


async def _regler(client, **valeurs):
    r = await client.put(REGLAGES, json=valeurs, headers=ENTETES)
    assert r.status_code == 200, r.text
    return r.json()


async def _activer(client):
    r = await client.post(f"/api/plugins/{ID}/activer", headers=ENTETES)
    assert r.status_code == 200, r.text
    return r.json()


async def _emettre(sorte, titre, quand, **kw):
    from backend.services import fil
    from backend.tests.conftest import test_session_factory

    async with test_session_factory() as s:
        await fil.emettre(s, sorte, titre, quand=quand, **kw)
        await s.commit()


async def _tick(quand):
    from backend.services import fil

    await fil.tick(quand)


async def test_une_alerte_critique_part_tout_de_suite_avec_le_lien_du_fil(charge, ntfy_serveur, monkeypatch):
    from backend.services import runtime_settings

    monkeypatch.setattr(runtime_settings, "_cache", {"adresse_reseau": "http://192.168.1.20:8090"})
    client = charge
    await _regler(client, serveur=ntfy_serveur.url, sujet="unisson-matin", jeton="tk_secret")
    await _activer(client)
    await _tick(_local(2026, 11, 10, 5, 0))  # premier passage : rien du passé
    await _emettre("disque.espace_bas", "Espace disque bas sur /music : prises en pause", _local(2026, 11, 10, 5, 51),
                   texte="Il reste 61 Go, minimum 50 Go.")
    await _emettre("import.rangee", "Nas — Illmatic", _local(2026, 11, 10, 5, 51), lien="/library/albums/1")
    await _tick(_local(2026, 11, 10, 5, 52))
    [recu] = ntfy_serveur.recus
    assert recu["auth"] == "Bearer tk_secret"
    assert recu["json"] == {
        "topic": "unisson-matin",
        "title": "Espace disque bas sur /music : prises en pause",
        "message": "Il reste 61 Go, minimum 50 Go.",
        "priority": 5,
        "tags": ["rotating_light"],
        "click": "http://192.168.1.20:8090/admin/fil",
        "actions": [{"action": "view", "label": "Ouvrir le fil", "url": "http://192.168.1.20:8090/admin/fil"}],
    }


async def test_le_resume_part_a_l_heure_reglee(charge, ntfy_serveur):
    client = charge
    await _regler(client, serveur=ntfy_serveur.url, sujet="unisson-matin", heure_resume="06:45",
                  lien_fil="https://unisson.example/admin/fil")
    await _activer(client)
    await _tick(_local(2026, 11, 9, 22, 0))
    for i in range(3):
        await _emettre("import.rangee", f"rangé {i}", _local(2026, 11, 10, 2, i), lien="/library/albums/1")
    await _emettre("import.deja_present", "Mobb Deep — The Infamous", _local(2026, 11, 10, 3, 0), lien="/import")
    await _tick(_local(2026, 11, 10, 6, 44))
    assert ntfy_serveur.recus == []
    await _tick(_local(2026, 11, 10, 6, 45))
    [recu] = ntfy_serveur.recus
    j = recu["json"]
    assert (j["title"], j["priority"], j["tags"], j["click"]) == (
        "unisson · 1 à décider · 3 rangés", 3, ["sunrise"], "https://unisson.example/admin/fil"
    )
    assert "• Mobb Deep — The Infamous" in j["message"].splitlines()
    assert recu["auth"] is None  # pas de jeton : sujet public


async def test_un_reglage_change_vaut_sans_reactiver(charge, ntfy_serveur):
    client = charge
    await _regler(client, serveur=ntfy_serveur.url, sujet="unisson-matin", gravite_alerte="critique")
    await _activer(client)
    await _tick(_local(2026, 11, 10, 5, 0))
    await _emettre("acquisition.echec", "Kaytranada — Ultra Light : en échec", _local(2026, 11, 10, 5, 1))
    await _tick(_local(2026, 11, 10, 5, 2))
    assert ntfy_serveur.recus == []
    await _regler(client, gravite_alerte="avertissement")
    await _emettre("acquisition.echec", "Little Simz — Lotus II : en échec", _local(2026, 11, 10, 5, 3))
    await _tick(_local(2026, 11, 10, 5, 4))
    # Le seuil abaissé vaut aussi pour l'échec de 5 h 01, encore dans la
    # fenêtre des alertes et jamais parti : les deux partent ensemble.
    [recu] = ntfy_serveur.recus
    assert (recu["json"]["title"], recu["json"]["priority"]) == ("2 alertes", 4)
    assert recu["json"]["message"].splitlines() == [
        "• Kaytranada — Ultra Light : en échec", "• Little Simz — Lotus II : en échec",
    ]


@pytest.mark.parametrize("panne", ["ferme", "refus"])
async def test_ntfy_en_panne_est_journalise_et_ne_bloque_rien(charge, ntfy_serveur, caplog, panne):
    client = charge
    serveur = port_ferme() if panne == "ferme" else ntfy_serveur.url
    ntfy_serveur.statut_force = 500 if panne == "refus" else None
    await _regler(client, serveur=serveur, sujet="unisson-matin", jeton="tk_secret")
    await _activer(client)
    await _tick(_local(2026, 11, 10, 5, 0))
    await _emettre("disque.espace_bas", "disque plein", _local(2026, 11, 10, 5, 1))
    with caplog.at_level(logging.WARNING):
        await _tick(_local(2026, 11, 10, 5, 2))
    lignes = [r.getMessage() for r in caplog.records if "ntfy.push" in r.getMessage()]
    assert lignes and ("injoignable" in lignes[0] if panne == "ferme" else "HTTP 500" in lignes[0])
    assert all("tk_secret" not in m for m in lignes)
    # Le fil, lui, reste lisible et compté.
    assert (await client.get("/api/fil/compteur")).json()["non_lus"] == 1
    # Le serveur revenu, l'alerte part au passage suivant (5 min plus tard).
    ntfy_serveur.statut_force = None
    if panne == "ferme":
        await _regler(client, serveur=ntfy_serveur.url)
    await _tick(_local(2026, 11, 10, 5, 8))
    assert [r["json"]["title"] for r in ntfy_serveur.recus] == ["disque plein"]


async def test_un_jeton_refuse_par_ntfy_est_un_echec_motive(charge, caplog):
    faux = FauxNtfy(jeton="tk_bon")
    try:
        client = charge
        await _regler(client, serveur=faux.url, sujet="unisson-matin", jeton="tk_mauvais")
        await _activer(client)
        await _tick(_local(2026, 11, 10, 5, 0))
        await _emettre("disque.espace_bas", "disque plein", _local(2026, 11, 10, 5, 1))
        with caplog.at_level(logging.WARNING):
            await _tick(_local(2026, 11, 10, 5, 2))
        assert faux.recus == []
        assert any("HTTP 401" in r.getMessage() for r in caplog.records)
    finally:
        faux.fermer()


async def test_sans_sujet_le_plugin_refuse_de_demarrer_avec_le_motif(charge):
    client = charge
    r = await client.post(f"/api/plugins/{ID}/activer", headers=ENTETES)
    plugin = next(p for p in (await client.get("/api/plugins")).json()["items"] if p["id"] == ID)
    assert plugin["etat"] == "erreur"
    assert "sujet ntfy à régler" in (plugin.get("motif") or "")
    assert r.status_code in (200, 409)


async def test_le_jeton_n_est_jamais_rendu(charge, ntfy_serveur):
    client = charge
    await _regler(client, serveur=ntfy_serveur.url, sujet="unisson-matin", jeton="tk_secret")
    vue = (await client.get(REGLAGES)).json()
    assert "tk_secret" not in str(vue)


async def test_desactiver_retire_le_canal(charge, ntfy_serveur):
    from backend.plugins import registres

    client = charge
    await _regler(client, serveur=ntfy_serveur.url, sujet="unisson-matin")
    await _activer(client)
    assert list(registres.canaux_notification.valeurs()) == ["ntfy.push"]
    r = await client.post(f"/api/plugins/{ID}/desactiver", headers=ENTETES)
    assert r.status_code == 200
    assert registres.canaux_notification.valeurs() == {}
    await _tick(_local(2026, 11, 10, 5, 0))
    await _emettre("disque.espace_bas", "disque plein", _local(2026, 11, 10, 5, 1))
    await _tick(_local(2026, 11, 10, 5, 2))
    assert ntfy_serveur.recus == []


def test_un_titre_accentue_part_en_json_intact():
    from ntfy.backend import corps
    from unisson.plugin import MessageNotification

    m = MessageNotification(genre="resume", titre="2 à décider · 38 rangés", texte="", gravite="info", lien=None)
    j = corps(m, "unisson-matin", None)
    assert (j["title"], j["message"], "click" in j) == ("unisson · 2 à décider · 38 rangés", "2 à décider · 38 rangés", False)


async def test_le_mot_de_passe_d_une_adresse_ne_part_pas_au_journal(charge, caplog):
    client = charge
    ferme = port_ferme().replace("http://", "http://alice:motdepasse@")
    await _regler(client, serveur=ferme, sujet="unisson-matin")
    await _activer(client)
    await _tick(_local(2026, 11, 10, 5, 0))
    await _emettre("disque.espace_bas", "disque plein", _local(2026, 11, 10, 5, 1))
    with caplog.at_level(logging.WARNING):
        await _tick(_local(2026, 11, 10, 5, 2))
    lignes = [r.getMessage() for r in caplog.records if "ntfy.push" in r.getMessage()]
    assert lignes and "***@127.0.0.1" in lignes[0]
    assert not any("motdepasse" in r.getMessage() or "alice" in r.getMessage() for r in caplog.records)


def test_un_long_message_est_coupe_sous_la_limite_de_ntfy():
    from ntfy.backend import MAX_OCTETS, corps
    from unisson.plugin import MessageNotification

    texte = "\n".join(f"• Arrivée à trier n° {i} — un titre accentué é è à" for i in range(400))
    m = MessageNotification(genre="resume", titre="400 à décider", texte=texte, gravite="info")
    message = corps(m, "unisson-matin", None)["message"]
    assert len(message.encode("utf-8")) <= MAX_OCTETS
    assert message.endswith("… (suite dans le fil)")
    assert message.startswith("• Arrivée à trier n° 0")
