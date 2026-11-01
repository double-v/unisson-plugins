"""La séance du réveil, de bout en bout, faux à la frontière seulement.

- l'ampli telnet : `faux_ampli` (un vrai serveur TCP, avec l'écho d'un AVR) ;
- le lecteur UPnP : `DmrAEtats` (un vrai serveur HTTP qui tient un état) ;
- le cœur : la vraie façade (`Contexte`), de vraies pistes en base et sur
  le disque, `adresse_reseau` réglée par la route publique des réglages ;
- des durées courtes (`Cadence`), jamais de faux entre deux modules.
"""

import asyncio
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from denon.backend import alarmes
from denon.backend.dlna import LecteurDlna
from denon.backend.lien import Config, Lien
from denon.backend.ordonnanceur import Ordonnanceur
from denon.backend.pilotes import PILOTES
from denon.backend.seance import Cadence, Seances
from denon.tests.aides import attendre, port_libre
from denon.tests.aides_reveil import PARIS, Horloge, a_paris, alarme, relire

CADENCE = Cadence(suivi_s=0.1, minute_s=1.0, attente_lien_s=0.5, essais_play=3, attente_play_s=0.5,
                  arret_s=1.0, marge_fin_s=0.3)


def contexte():
    from backend.plugins.fiche import Fiche
    from unisson.plugin import Contexte

    return Contexte(Fiche(id="denon", nom="Denon", version="0.3.0", description="", categorie="officiel",
                          coeur=">=0.5", actif_par_defaut=False))


@dataclass
class Banc:
    ampli: object
    dmr: object
    lien: Lien
    seances: Seances
    ordo: Ordonnanceur
    session: object
    superviseur: asyncio.Task

    async def poser(self, **champs) -> dict:
        test = champs.pop("_test", False)
        async with self.session() as s:
            a = await alarmes.creer(s, alarmes.valider(alarme(**champs)), a_paris("2026-11-05T22:00"), test=test)
            await s.commit()
        return a

    async def lancer(self, **champs) -> tuple[dict, str]:
        a = await self.poser(**champs)
        return a, await self.seances.lancer(a, ecrire=True)

    async def fin(self, delai: float = 10) -> str:
        tache = self.seances._tache
        await asyncio.wait_for(asyncio.shield(tache), delai)
        return self.seances.derniere["resultat"]

    def telnet(self) -> list[str]:
        return [c for c in self.ampli.commandes if c not in ("PW?", "MV?", "MU?", "SI?")]


@pytest_asyncio.fixture
async def banc(client, table, faux_ampli, dmr):
    taches = []

    async def fabriquer(cadence: Cadence = CADENCE, delai: float = 0.05, port: int | None = None) -> Banc:
        faux_ampli.echo = True
        lien = Lien(lambda: Config("127.0.0.1", port or faux_ampli.port, 0.01), PILOTES["avrx4000"],
                    attente_min=0.05, attente_max=0.2)
        taches.append(asyncio.create_task(lien.tourner()))
        if port is None:
            await attendre(lambda: lien.connecte and lien.en_attente == 0)
            await asyncio.sleep(0.05)
        lecteur = LecteurDlna(f"{dmr.base}/description.xml", delai=1)
        ordo = Ordonnanceur(table, lambda: PARIS)
        seances = Seances(contexte(), lien, lecteur, table, fuseau=lambda: PARIS, delai_reveil_s=lambda: delai,
                          cadence=cadence, ordonnanceur=ordo)
        ordo.declencher = seances.declencher
        superviseur = asyncio.create_task(seances.tourner())
        taches.append(superviseur)
        return Banc(faux_ampli, dmr, lien, seances, ordo, table, superviseur)

    yield fabriquer
    for t in reversed(taches):
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)


async def comptes(db_session) -> dict[int, int]:
    lignes = await db_session.execute(text("SELECT id, play_count FROM tracks ORDER BY id"))
    db_session.expire_all()
    return {i: n for i, n in lignes.all()}


async def playlist(db_session, ids: list[int]) -> int:
    pid = (await db_session.execute(
        text("INSERT INTO playlists (name, created_at, updated_at) VALUES ('Matin', 'x', 'x') RETURNING id"))).scalar_one()
    for i, t in enumerate(ids):
        await db_session.execute(
            text("INSERT INTO playlist_items (playlist_id, track_id, position, added_at) VALUES (:p, :t, :i, 'x')"),
            {"p": pid, "t": t, "i": i})
    await db_session.commit()
    return pid


def url_de(adresse: str, piste: int) -> str:
    return f"{adresse}/api/flux/{piste}/original.flac"


# ── les trois modes de fin ──────────────────────────────────────────────


async def test_fin_apres_deux_pistes_par_setnext_puis_veille(banc, adresse, pistes, db_session):
    b = await banc()
    pl = await playlist(db_session, pistes[:3])
    a, code = await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=2, montee_s=0,
                             volume_cible_db=-40)
    assert code == "en_cours"
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "en_cours"
    assert await b.fin() == "joue"

    # Allumer, volume (cible d'emblée : pas de montée), source réseau ; puis
    # volume et source renvoyés après la sortie de veille ; veille à la fin.
    assert b.telnet() == ["PWON", "MV400", "SINET", "MV400", "SINET", "PWSTANDBY"]
    # Une seule mise en place : la seconde piste enchaîne par SetNext.
    assert b.dmr.uris("SetAVTransportURI") == [url_de(adresse, pistes[0])]
    assert b.dmr.uris("SetNextAVTransportURI") == [url_de(adresse, pistes[1])]
    assert b.dmr.jouees == [url_de(adresse, pistes[0]), url_de(adresse, pistes[1])]
    # marquer_jouee une fois par piste jouée, jamais pour la troisième.
    assert await comptes(db_session) == {pistes[0]: 1, pistes[1]: 1, **{p: 0 for p in pistes[2:]}}
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "joue"
    # Le DIDL porte titre, artiste et durée.
    didl = b.dmr.soaps[[r.action for r in b.dmr.soaps].index("SetAVTransportURI")].arguments["CurrentURIMetaData"]
    assert "Piste 1" in didl and "Test Artist" in didl and 'duration="0:00:01.600"' in didl


async def test_fin_a_la_duree_stop_puis_veille(banc, adresse, pistes):
    b = await banc()
    _, code = await b.lancer(fin_mode="duree", fin_valeur=2, montee_s=0)  # 2 « minutes » de 1 s
    assert code == "en_cours"
    vue = b.seances.vue()["seance"]
    assert vue["fin_mode"] == "duree" and vue["fin_prevue"] is not None
    assert await b.fin() == "joue"
    assert b.dmr.actions()[-1] == "Stop"
    assert b.telnet()[-1] == "PWSTANDBY"
    # 2 s de musique : au moins deux pistes de 1,6 s ont commencé.
    assert len(b.dmr.jouees) >= 2


async def test_sans_limite_recharge_et_ne_se_met_jamais_en_veille(banc, adresse, pistes, db_session):
    b = await banc()
    pl = await playlist(db_session, pistes[:2])
    _, code = await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    assert code == "en_cours"
    # La playlist (2 pistes) est rejouée : le lot se recharge.
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.jouees >= 3, delai=8)
    assert b.seances.en_cours
    assert await b.seances.arreter() is True
    assert await b.fin() == "arretee"
    assert "PWSTANDBY" not in b.telnet()
    assert b.dmr.actions()[-1] == "Stop"  # arrêter coupe la musique, pas l'ampli
    assert (await comptes(db_session))[pistes[0]] == 2


# ── le volume ───────────────────────────────────────────────────────────


async def test_la_montee_va_du_depart_a_la_cible_par_demi_db(banc, adresse, pistes):
    b = await banc()
    await b.lancer(fin_mode="sans_limite", fin_valeur=None, volume_depart_db=-50, volume_cible_db=-48, montee_s=1)
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.montee == "finie", delai=5)
    mv = [c for c in b.telnet() if c.startswith("MV")]
    assert mv == ["MV300", "MV300", "MV305", "MV310", "MV315", "MV320"]
    assert b.lien.etat["volume"] == -48


async def test_la_montee_s_arrete_quand_on_touche_au_volume(banc, adresse, pistes):
    b = await banc()
    await b.lancer(fin_mode="sans_limite", fin_valeur=None, volume_depart_db=-60, volume_cible_db=-40, montee_s=4)
    await attendre(lambda: sum(c.startswith("MV") for c in b.telnet()) >= 5, delai=5)
    await b.ampli.pousser("MV25\r")  # quelqu'un baisse à -55 dB
    await attendre(lambda: b.seances.courante.montee == "interrompue", delai=3)
    envoyes = sum(c.startswith("MV") for c in b.telnet())
    await asyncio.sleep(0.6)
    assert sum(c.startswith("MV") for c in b.telnet()) == envoyes
    assert b.seances.en_cours  # la musique continue
    assert b.seances.vue()["seance"]["volume"] == -55


# ── l'enchaînement et le repli ──────────────────────────────────────────


@pytest.mark.parametrize("panne", ["setnext_refuse", "pas_d_enchainement"])
async def test_repli_par_set_av_transport_uri(banc, adresse, pistes, db_session, panne):
    b = await banc()
    if panne == "setnext_refuse":
        b.dmr.refuser_suivante = True
    else:
        b.dmr.enchaine = False
    pl = await playlist(db_session, pistes[:3])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=3, montee_s=0)
    assert await b.fin() == "joue"
    assert b.dmr.uris("SetAVTransportURI") == [url_de(adresse, p) for p in pistes[:3]]
    assert b.dmr.jouees == [url_de(adresse, p) for p in pistes[:3]]
    assert b.seances.derniere["enchainement"] == "repli"
    assert await comptes(db_session) == {**{p: 1 for p in pistes[:3]}, **{p: 0 for p in pistes[3:]}}
    assert b.telnet()[-1] == "PWSTANDBY"


async def test_play_reessaye_pendant_la_sortie_de_veille(banc, adresse, pistes):
    b = await banc()
    b.dmr.refus_play = 2
    await b.lancer(fin_mode="pistes", fin_valeur=1, montee_s=0)
    assert await b.fin() == "joue"
    assert b.dmr.actions().count("Play") == 3


async def test_play_toujours_refuse(banc, adresse, pistes):
    b = await banc()
    b.dmr.refus_play = 99
    a, _ = await b.lancer(fin_mode="pistes", fin_valeur=1, montee_s=0)
    assert await b.fin() == "lecture_impossible"
    assert b.dmr.actions().count("Play") == 3
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "lecture_impossible"


async def test_une_piste_sans_fichier_est_sautee(banc, adresse, pistes, db_session, music_root):
    b = await banc()
    (music_root / "Rap Francophone/Test Artist/Album One/02.flac").unlink()
    pl = await playlist(db_session, pistes[:3])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=3, montee_s=0)
    assert await b.fin() == "joue"
    assert b.dmr.jouees == [url_de(adresse, pistes[0]), url_de(adresse, pistes[2])]
    assert [s["piste"] for s in b.seances.derniere["sautees"]] == [pistes[1]]
    assert b.seances.derniere["sautees"][0]["code"] == "fichier_absent"
    assert (await comptes(db_session))[pistes[1]] == 0


# ── ce qui empêche de partir ────────────────────────────────────────────


async def test_sans_adresse_reseau_rien_n_est_envoye(banc, pistes):
    b = await banc()
    a, code = await b.lancer(montee_s=0)
    assert code == "adresse_reseau_non_reglee"
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "adresse_reseau_non_reglee"
    assert b.telnet() == [] and b.dmr.soaps == []
    assert not b.seances.en_cours


async def test_ampli_injoignable_en_telnet(banc, adresse, pistes):
    b = await banc(port=port_libre())
    a, code = await b.lancer(montee_s=0)
    assert code == "ampli_injoignable"
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "ampli_injoignable"
    assert b.dmr.soaps == []


async def test_ampli_injoignable_en_upnp(banc, adresse, pistes):
    b = await banc()
    await b.dmr.arreter()
    _, code = await b.lancer(montee_s=0)
    assert code == "ampli_injoignable"
    assert b.telnet() == []


async def test_aucune_piste(banc, adresse, sample_data):
    b = await banc()
    _, code = await b.lancer(montee_s=0)
    assert code == "aucune_piste"
    assert b.telnet() == []


async def test_aucun_format_commun(banc, adresse, pistes):
    from denon.tests.aides_seance import _enveloppe, CM

    b = await banc()
    b.dmr.reponses[("/ConnectionManager/ctrl", "GetProtocolInfo")] = (
        200, _enveloppe("GetProtocolInfo", {"Source": "", "Sink": "http-get:*:audio/mpeg:*"}, CM))
    _, code = await b.lancer(montee_s=0)
    assert code == "aucun_format_commun"
    assert b.telnet() == []


async def test_une_alarme_qui_echoue_laisse_jouer_la_seance_en_cours(banc, adresse, pistes):
    b = await banc()
    await b.lancer(fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING")
    _, code = await b.lancer(contexte="album", contexte_id=pistes[0] + 10_000, montee_s=0)
    assert code == "contexte_inconnu"
    assert b.seances.en_cours


# ── quelqu'un reprend la main ───────────────────────────────────────────


@pytest.mark.parametrize("geste", ["autre_source", "stop", "pause", "autre_media", "veille"])
async def test_reprise_de_la_main_sans_mise_en_veille(banc, adresse, pistes, geste):
    b = await banc()
    a, _ = await b.lancer(fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING" and b.lien.etat["source"] == "NET", delai=3)
    await asyncio.sleep(0.15)
    if geste == "autre_source":
        await b.ampli.pousser("SITV\r")
    elif geste == "stop":
        b.dmr.stop_externe()  # en milieu de piste : pas une fin de piste
    elif geste == "pause":
        b.dmr.pause_externe()
    elif geste == "autre_media":
        b.dmr.jouer_autre("http://192.0.2.50/radio.mp3")
    else:
        await b.ampli.pousser("PWSTANDBY\r")
    assert await b.fin(3) == "reprise_en_main"
    assert "PWSTANDBY" not in b.telnet()
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "reprise_en_main"


# ── une seule séance à la fois ──────────────────────────────────────────


async def test_une_alarme_remplace_la_seance_en_cours(banc, adresse, pistes, db_session):
    b = await banc()
    premiere, _ = await b.lancer(nom="Première", fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING")
    pl = await playlist(db_session, pistes[3:4])
    seconde, code = await b.lancer(nom="Seconde", contexte="playlist", contexte_id=pl, fin_mode="pistes",
                                   fin_valeur=1, montee_s=0)
    assert code == "en_cours"
    assert (await relire(b.session, premiere["id"]))["dernier_resultat"] == "remplacee"
    assert b.seances.vue()["seance"]["alarme"]["nom"] == "Seconde"
    assert await b.fin() == "joue"
    assert b.dmr.jouees[-1] == url_de(adresse, pistes[3])
    assert (await relire(b.session, seconde["id"]))["dernier_resultat"] == "joue"


# ── par le vrai ordonnanceur ────────────────────────────────────────────


async def test_l_ordonnanceur_lance_la_seance(banc, adresse, pistes):
    b = await banc()
    horloge = Horloge(a_paris("2026-11-05T22:00"))
    b.ordo.maintenant = horloge
    a = await b.poser(heure="07:00", jours=0, fin_mode="pistes", fin_valeur=1, montee_s=0, _test=True)
    horloge.t = a_paris("2026-11-06T07:00:00.200")
    await b.ordo.passer()
    assert b.seances.en_cours
    # L'alarme de test est déjà supprimée ; son résumé attend la fin.
    assert b.ordo.tests[a["id"]]["dernier_resultat"] == "en_cours"
    assert await b.fin() == "joue"
    assert b.ordo.tests[a["id"]]["dernier_resultat"] == "joue"
    assert len(b.dmr.jouees) == 1 and b.telnet()[0] == "PWON"


async def test_l_ordonnanceur_note_un_echec_de_preparation(banc, pistes):
    b = await banc()
    horloge = Horloge(a_paris("2026-11-05T22:00"))
    b.ordo.maintenant = horloge
    a = await b.poser(heure="07:00", montee_s=0)
    horloge.t = a_paris("2026-11-06T07:00:00.200")
    await b.ordo.passer()
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "adresse_reseau_non_reglee"


async def test_arreter_sans_seance(banc):
    b = await banc()
    assert await b.seances.arreter() is False
    assert b.seances.vue() == {"seance": None, "derniere": None}


async def test_la_fin_du_superviseur_arrete_la_seance_et_ferme_tout(banc, adresse, pistes):
    b = await banc()
    a, _ = await b.lancer(fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING")
    b.superviseur.cancel()
    await asyncio.gather(b.superviseur, return_exceptions=True)
    assert not b.seances.en_cours
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "plugin_desactive"
    await attendre(lambda: b.dmr.ouvertes == 0)
    assert not [t for t in asyncio.all_tasks() if t.get_name().startswith("denon:seance")]
