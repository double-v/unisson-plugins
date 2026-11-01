"""Les routes de la séance par le vrai chargeur : `essayer`, `seance`,
`arreter`, `diagnostic`, le testeur de fuseau qui joue pour de bon, et la
désactivation pendant une séance.

Le plugin est réglé comme en production (hôte telnet, `hote_upnp`, jeton),
sur le faux ampli TCP et le DMR à états ; seul `delai_reveil_s` est mis à 0.
"""

import asyncio
import time as chrono

from denon.tests.aides import attendre
from denon.tests.aides_reveil import AUTH, JETON, RACINE, alarme, lire_alarme, regler


async def activer(client, faux_ampli, dmr, denon_installe):
    faux_ampli.echo = True
    await regler(client, hote="127.0.0.1", port_telnet=faux_ampli.port, cadence_ms=10, jeton=JETON,
                 hote_upnp=f"{dmr.base}/description.xml", delai_reveil_s="0")
    await denon_installe()
    await attendre(lambda: len(faux_ampli.commandes) >= 4)


async def creer(client, **champs) -> dict:
    r = await client.post(f"{RACINE}/alarmes", json=alarme(**champs), headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


async def seance_en_lecture(client, delai: float = 8) -> dict:
    debut = chrono.monotonic()
    while True:
        vue = (await client.get(f"{RACINE}/seance", headers=AUTH)).json()["seance"]
        if vue and vue["etat"] == "lecture":
            return vue
        assert chrono.monotonic() - debut < delai, vue
        await asyncio.sleep(0.05)


async def test_le_jeton_est_exige(client, faux_ampli, dmr, denon_installe):
    await activer(client, faux_ampli, dmr, denon_installe)
    for methode, chemin in (("POST", "/alarmes/1/essayer"), ("GET", "/seance"), ("POST", "/seance/arreter"),
                            ("GET", "/diagnostic")):
        r = await client.request(methode, RACINE + chemin)
        assert r.status_code == 401, (methode, chemin)


async def test_essayer_suivre_puis_arreter(client, faux_ampli, dmr, denon_installe, adresse, pistes):
    await activer(client, faux_ampli, dmr, denon_installe)
    a = await creer(client, fin_mode="sans_limite", fin_valeur=None, montee_s=0, volume_cible_db=-42)

    r = await client.post(f"{RACINE}/alarmes/{a['id']}/essayer", headers=AUTH)
    assert r.status_code == 202, r.text
    assert r.json()["resultat"] == "en_cours" and r.json()["seance"]["alarme"] == {"id": a["id"], "nom": "Semaine"}
    assert (await lire_alarme(client, a["id"]))["dernier_resultat"] == "en_cours"

    vue = await seance_en_lecture(client)
    assert vue["piste"]["titre"].startswith("Piste ") and vue["piste"]["artiste"] == "Test Artist"
    assert vue["piste"]["album"] == "Album One" and vue["piste"]["pochette"] is None
    assert vue["volume"] == -42 and vue["fin_mode"] == "sans_limite" and vue["fin_prevue"] is None
    assert faux_ampli.commandes[4:7] == ["PWON", "MV380", "SINET"]

    r = await client.post(f"{RACINE}/seance/arreter", headers=AUTH)
    assert r.status_code == 200
    corps = r.json()
    assert corps["arretee"] is True and corps["seance"] is None and corps["derniere"]["resultat"] == "arretee"
    assert dmr.actions()[-1] == "Stop" and "PWSTANDBY" not in faux_ampli.commandes
    assert (await lire_alarme(client, a["id"]))["dernier_resultat"] == "arretee"
    # Plus rien à arrêter.
    assert (await client.post(f"{RACINE}/seance/arreter", headers=AUTH)).json()["arretee"] is False

    assert (await client.post(f"{RACINE}/alarmes/999999/essayer", headers=AUTH)).status_code == 404


async def test_essayer_sans_adresse_reseau(client, faux_ampli, dmr, denon_installe, pistes):
    await activer(client, faux_ampli, dmr, denon_installe)
    a = await creer(client)
    r = await client.post(f"{RACINE}/alarmes/{a['id']}/essayer", headers=AUTH)
    assert r.status_code == 409
    corps = r.json()
    assert corps["error"] == "adresse_reseau_non_reglee" and corps["reglage"] == "/admin/settings#reseau"
    assert corps["message"]
    assert (await lire_alarme(client, a["id"]))["dernier_resultat"] == "adresse_reseau_non_reglee"
    assert faux_ampli.commandes[4:] == []  # l'ampli n'a pas été réveillé pour rien


async def test_le_diagnostic(client, faux_ampli, dmr, denon_installe, adresse):
    await activer(client, faux_ampli, dmr, denon_installe)
    d = (await client.get(f"{RACINE}/diagnostic", headers=AUTH)).json()
    assert d["ok"] is True and d["problemes"] == []
    assert d["telnet"]["connecte"] is True and d["telnet"]["port"] == faux_ampli.port
    assert d["upnp"]["joignable"] is True and d["upnp"]["description"] == f"{dmr.base}/description.xml"
    assert "http-get:*:audio/x-flac:*" in d["upnp"]["formats"] and len(d["upnp"]["formats"]) == 4
    assert d["adresse_reseau"] == {"reglee": True, "adresse": adresse, "reglage": "/admin/settings#reseau", "message": None}
    assert d["pilote"]["plafond"] == {"frequence_max": 96000, "profondeur_max": 24}
    assert d["pilote"]["source_reseau"] == "SINET" and d["pilote"]["delai_reveil_s"] == 0
    assert {c["code"] for c in d["conseils"]} == {"controle_reseau", "ip_fixe"}
    assert d["horloge"]["fuseau"] == "Europe/Paris" and d["horloge"]["utc"].endswith("Z")
    assert d["seance"] is None


async def test_le_diagnostic_dit_ce_qui_ne_va_pas(client, faux_ampli, dmr, denon_installe):
    await activer(client, faux_ampli, dmr, denon_installe)
    await dmr.arreter()
    d = (await client.get(f"{RACINE}/diagnostic", headers=AUTH)).json()
    assert d["ok"] is False
    assert set(d["problemes"]) == {"upnp_injoignable", "adresse_reseau_non_reglee"}
    assert d["upnp"]["joignable"] is False and d["upnp"]["erreur"]
    assert d["adresse_reseau"]["reglee"] is False and d["adresse_reseau"]["reglage"] == "/admin/settings#reseau"
    # Sans hôte du tout, l'adresse UPnP ne se forme pas : dit, pas une 500.
    await regler(client, hote="", hote_upnp="")
    d = (await client.get(f"{RACINE}/diagnostic", headers=AUTH)).json()
    assert d["upnp"]["description"] is None and "hote" in d["upnp"]["erreur"]


async def test_le_testeur_de_cinq_secondes_joue_une_piste(client, faux_ampli, dmr, denon_installe, adresse, pistes):
    """Le chemin complet : le testeur crée l'alarme, le vrai ordonnanceur la
    fait partir, la séance joue une piste et met l'ampli en veille."""
    await activer(client, faux_ampli, dmr, denon_installe)
    test = (await client.post(f"{RACINE}/tester", json={"dans_s": 5}, headers=AUTH)).json()["alarme"]
    debut = chrono.monotonic()
    while (res := (await client.get(f"{RACINE}/tester/{test['id']}", headers=AUTH)).json())["dernier_resultat"] != "joue":
        assert chrono.monotonic() - debut < 15, res
        await asyncio.sleep(0.1)
    assert res["etat"] == "partie"
    assert len(dmr.jouees) == 1 and faux_ampli.commandes[-1] == "PWSTANDBY"


async def test_desactiver_pendant_une_seance_ne_laisse_rien(client, faux_ampli, dmr, denon_installe, adresse, pistes):
    from backend.plugins import chargeur

    await activer(client, faux_ampli, dmr, denon_installe)
    a = await creer(client, fin_mode="sans_limite", fin_valeur=None, montee_s=600, volume_depart_db=-60)
    assert (await client.post(f"{RACINE}/alarmes/{a['id']}/essayer", headers=AUTH)).status_code == 202
    await seance_en_lecture(client)

    await chargeur.desactiver("denon")
    await attendre(lambda: not [t for t in asyncio.all_tasks() if t.get_name().startswith(("denon:", "plugin:denon"))])
    await attendre(lambda: faux_ampli.fermetures == 1 and dmr.ouvertes == 0)
    assert "PWSTANDBY" not in faux_ampli.commandes
    assert (await client.get(f"{RACINE}/seance", headers=AUTH)).status_code == 404
