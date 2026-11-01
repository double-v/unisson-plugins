"""La séance du réveil, de bout en bout, faux à la frontière seulement.

- l'ampli telnet : `faux_ampli` (un vrai serveur TCP, avec l'écho d'un AVR) ;
- le lecteur UPnP : `DmrAEtats` (un vrai serveur HTTP qui tient un état) ;
- le cœur : la vraie façade (`Contexte`), de vraies pistes en base et sur
  le disque, `adresse_reseau` réglée par la route publique des réglages ;
- des durées courtes (`Cadence`), jamais de faux entre deux modules.
"""

import asyncio
import contextlib
import time as chrono
from dataclasses import dataclass, replace

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
                  arret_s=1.0, marge_fin_s=0.3, budget_arret_s=2.0)


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

    async def fin(self, delai: float = 25) -> str:
        tache = self.seances._tache
        await asyncio.wait_for(asyncio.shield(tache), delai)
        return self.seances.derniere["resultat"]

    def telnet(self) -> list[str]:
        return [c for c in self.ampli.commandes if c not in ("PW?", "MV?", "MU?", "SI?")]


@pytest_asyncio.fixture
async def banc(client, table, faux_ampli, dmr):
    taches, bancs = [], []

    async def fabriquer(cadence: Cadence = CADENCE, delai: float = 0.05, port: int | None = None,
                        session=None) -> Banc:
        faux_ampli.echo = True
        lien = Lien(lambda: Config("127.0.0.1", port or faux_ampli.port, 0.01), PILOTES["avrx4000"],
                    attente_min=0.05, attente_max=0.2)
        taches.append(asyncio.create_task(lien.tourner()))
        if port is None:
            await attendre(lambda: lien.connecte and lien.en_attente == 0)
            await asyncio.sleep(0.05)
        lecteur = LecteurDlna(f"{dmr.base}/description.xml", delai=1)
        ordo = Ordonnanceur(table, lambda: PARIS)
        seances = Seances(contexte(), lien, lecteur, session or table, fuseau=lambda: PARIS, delai_reveil_s=lambda: delai,
                          cadence=cadence, ordonnanceur=ordo)
        ordo.declencher = seances.declencher
        superviseur = asyncio.create_task(seances.tourner())
        taches.append(superviseur)
        bancs.append(banc_ := Banc(faux_ampli, dmr, lien, seances, ordo, table, superviseur))
        return banc_

    yield fabriquer
    for t in reversed(taches):
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
    for b in bancs:  # aucun appel en base ne survit au test
        await attendre(lambda: not b.seances.en_vol, delai=10)


@pytest_asyncio.fixture
async def longues(db_session, sample_data, music_root, tmp_path):
    """Deux pistes de 30 s et une sans durée connue : un geste « en milieu
    de piste » le reste, même sous charge."""
    from backend.tests.bibliotheque_flux import piste

    fichier = tmp_path / "longue.flac"
    fichier.write_bytes(b"fLaC" + bytes(64))
    album = sample_data["album1"]
    return [
        await piste(db_session, album, music_root, fichier, nom=nom, format="FLAC", sample_rate=44100,
                    bits_per_sample=16, duration_seconds=duree, title_tag=nom)
        for nom, duree in (("l1.flac", 30.0), ("l2.flac", 30.0), ("sans-duree.flac", None))
    ]


def session_lente(table, retard: float = 0.4):
    """La base qui met du temps à répondre (la frontière, pas un module)."""

    @contextlib.asynccontextmanager
    async def ouvrir():
        await asyncio.sleep(retard)
        async with table() as s:
            yield s

    return ouvrir


def volumes(b) -> list[float]:
    from denon.backend.pilotes import lire_volume

    return [lire_volume(c[2:]) for c in b.telnet() if c.startswith("MV")]


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


def _coeur_07() -> bool:
    from unisson.plugin import VERSION_COEUR

    return tuple(int(x) for x in VERSION_COEUR.split(".")[:2]) >= (0, 7)


@pytest.mark.skipif("not _coeur_07()",
                    reason="playlists dynamiques -1/-2 dans ctx.pistes_playlist : cœur 0.7 (unisson#1077) attendu")
async def test_la_playlist_des_pistes_favorites_passe_par_la_facade(banc, adresse, pistes, db_session):
    b = await banc()
    favorites = [pistes[2], pistes[0]]
    for t in favorites:
        await db_session.execute(text("INSERT INTO favorites (track_id, created_at) VALUES (:t, 'x')"), {"t": t})
    await db_session.commit()
    a, code = await b.lancer(contexte="playlist", contexte_id=alarmes.PLAYLIST_PISTES_FAVORITES,
                             fin_mode="pistes", fin_valeur=5, montee_s=0)
    assert code == "en_cours"
    assert await b.fin() == "joue"
    # Rien que les favorites, chacune une fois (l'ordre est celui du cœur).
    assert sorted(b.dmr.jouees) == sorted(url_de(adresse, t) for t in favorites)
    assert await comptes(db_session) == {p: int(p in favorites) for p in pistes}


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
    assert "Piste 1" in didl and "Test Artist" in didl and 'duration="0:00:03.000"' in didl


async def test_fin_a_la_duree_stop_puis_veille(banc, adresse, pistes):
    b = await banc()
    _, code = await b.lancer(fin_mode="duree", fin_valeur=4, montee_s=0)  # 4 « minutes » de 1 s
    assert code == "en_cours"
    vue = b.seances.vue()["seance"]
    assert vue["fin_mode"] == "duree" and vue["fin_prevue"] is not None
    assert await b.fin() == "joue"
    assert b.dmr.actions()[-1] == "Stop"
    assert b.telnet()[-1] == "PWSTANDBY"
    # 4 s de musique : au moins deux pistes de 3 s ont commencé.
    assert len(b.dmr.jouees) >= 2


async def test_sans_limite_recharge_et_ne_se_met_jamais_en_veille(banc, adresse, pistes, db_session):
    b = await banc()
    pl = await playlist(db_session, pistes[:2])
    _, code = await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    assert code == "en_cours"
    # La playlist (2 pistes) est rejouée : le lot se recharge.
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.jouees >= 3, delai=20)
    assert b.seances.en_cours
    assert await b.seances.arreter() is True
    assert await b.fin() == "arretee"
    assert "PWSTANDBY" not in b.telnet()
    assert b.dmr.actions()[-1] == "Stop"  # arrêter coupe la musique, pas l'ampli
    assert (await comptes(db_session))[pistes[0]] == 2


# ── le volume ───────────────────────────────────────────────────────────


async def test_la_montee_va_du_depart_a_la_cible_par_demi_db(banc, adresse, longues, db_session):
    b = await banc()
    pl = await playlist(db_session, longues[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None,
                   volume_depart_db=-50, volume_cible_db=-46, montee_s=1)
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.montee == "finie", delai=15)
    v = volumes(b)
    assert v[0] == -50 and v[-1] == -46  # part du départ, finit à la cible
    assert v == sorted(v) and all(-50 <= x <= -46 for x in v)  # monotone, bornée
    assert all(round(x * 2) == x * 2 for x in v)  # par demi-dB
    await attendre(lambda: b.lien.etat["volume"] == -46)


async def test_une_baisse_pendant_la_montee_l_arrete(banc, adresse, longues, db_session):
    b = await banc()
    pl = await playlist(db_session, longues[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None,
                   volume_depart_db=-60, volume_cible_db=-40, montee_s=8)
    await attendre(lambda: len(volumes(b)) >= 6 and b.lien.etat["volume"] == volumes(b)[-1], delai=15)
    # Quelqu'un baisse à la télécommande, jusqu'au volume de départ : une
    # valeur que la montée a déjà envoyée.
    await b.ampli.pousser("MV20\r")
    await attendre(lambda: b.seances.courante.montee == "interrompue", delai=10)
    envoyes = len(volumes(b))
    await asyncio.sleep(0.8)  # 4 pas auraient suivi
    assert len(volumes(b)) == envoyes
    assert b.seances.en_cours  # la musique continue
    assert b.seances.vue()["seance"]["volume"] == -60


async def test_une_baisse_d_un_cran_pendant_la_montee_l_arrete(banc, adresse, longues, db_session):
    b = await banc()
    pl = await playlist(db_session, longues[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None,
                   volume_depart_db=-60, volume_cible_db=-40, montee_s=8)
    await attendre(lambda: len(volumes(b)) >= 6 and b.lien.etat["volume"] == volumes(b)[-1], delai=15)
    dernier = volumes(b)[-1]
    await b.ampli.pousser(f"{PILOTES['avrx4000'].volume(dernier - 0.5)}\r")  # un cran plus bas : notre avant-dernier pas
    await attendre(lambda: b.seances.courante.montee == "interrompue", delai=10)
    envoyes = len(volumes(b))
    await asyncio.sleep(0.8)
    assert len(volumes(b)) == envoyes


async def test_des_echos_perdus_n_arretent_pas_la_montee(banc, adresse, longues, db_session):
    b = await banc()
    b.ampli.sans_echo = {"MV305", "MV310"}  # deux pas de suite sans écho
    pl = await playlist(db_session, longues[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None,
                   volume_depart_db=-50, volume_cible_db=-47, montee_s=2)
    await attendre(lambda: b.seances.courante is not None
                   and b.seances.courante.montee in ("finie", "interrompue"), delai=15)
    assert b.seances.courante.montee == "finie"
    assert volumes(b)[-1] == -47


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


async def test_un_stopped_juste_apres_l_enchainement_n_est_pas_une_reprise(banc, adresse, pistes, db_session):
    b = await banc()
    b.dmr.pause_au_passage = 0.35  # moins que attente_play_s : l'ampli passe par STOPPED
    pl = await playlist(db_session, pistes[:2])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=2, montee_s=0)
    assert await b.fin() == "joue"
    assert b.dmr.jouees == [url_de(adresse, p) for p in pistes[:2]]
    assert b.telnet()[-1] == "PWSTANDBY"


async def test_au_repli_une_piste_qui_ne_demarre_pas_est_sautee(banc, adresse, pistes, db_session):
    b = await banc()
    b.dmr.enchaine = False
    b.dmr.urls_refusees = {url_de(adresse, pistes[1])}
    pl = await playlist(db_session, pistes[:3])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=3, montee_s=0)
    assert await b.fin() == "joue"
    assert b.dmr.jouees == [url_de(adresse, pistes[0]), url_de(adresse, pistes[2])]
    assert [(s["piste"], s["code"]) for s in b.seances.derniere["sautees"]] == [(pistes[1], "lecture_refusee")]
    assert (await comptes(db_session))[pistes[1]] == 0


async def test_un_reltime_a_zero_juste_avant_la_fin_n_est_pas_une_reprise(banc, adresse, pistes, db_session):
    """GetTransportInfo dit PLAYING, puis GetPositionInfo, lu juste après la
    fin de piste, rend RelTime 0 : le début de la piste ne recule pas. Ici,
    RelTime reste à 0 jusqu'à la fin, pour que le dernier suivi le voie."""
    b = await banc()
    pl = await playlist(db_session, pistes[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=1, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING" and b.dmr.temps() >= 2.2, delai=15)
    b.dmr.reltime_zero = 10_000
    assert await b.fin() == "joue"
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
    # L'ampli allumé pour rien est rendu à la veille.
    assert b.dmr.actions()[-1] == "Stop"
    assert b.telnet()[-1] == "PWSTANDBY"


async def test_une_erreur_apres_l_allumage_remet_l_ampli_en_veille(banc, adresse, pistes):
    b = await banc()
    a = await b.poser(fin_mode="pistes", fin_valeur=1, montee_s=0)
    a["volume_cible_db"] = "fort"  # une alarme que rien ne valide plus : erreur à l'envoi du volume
    assert await b.seances.lancer(a) == "en_cours"
    assert await b.fin() == "erreur:TypeError"
    assert b.telnet() == ["PWON", "PWSTANDBY"]
    assert "Stop" not in b.dmr.actions()  # aucune piste posée


async def test_duree_upnp_perdu_veille_par_telnet_a_l_echeance(banc, adresse, longues, db_session):
    b = await banc()
    pl = await playlist(db_session, longues[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="duree", fin_valeur=2, montee_s=0)
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.etat == "lecture", delai=10)
    await b.dmr.arreter()  # l'ampli ne répond plus en UPnP
    await asyncio.sleep(0.6)
    assert b.seances.en_cours  # la séance sonde encore
    assert await b.fin() == "ampli_injoignable"
    assert b.telnet()[-1] == "PWSTANDBY"


@pytest.mark.parametrize("mode, veille", [("pistes", True), ("sans_limite", False)])
async def test_upnp_perdu_en_pistes_veille_en_sans_limite_non(banc, adresse, longues, db_session, mode, veille):
    b = await banc()
    pl = await playlist(db_session, longues[:2])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode=mode, fin_valeur=2 if mode == "pistes" else None,
                   montee_s=0)
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.etat == "lecture", delai=10)
    await b.dmr.arreter()  # l'ampli ne répond plus en UPnP
    assert await b.fin() == "ampli_injoignable"
    assert (b.telnet()[-1] == "PWSTANDBY") is veille
    assert ("PWSTANDBY" in b.telnet()) is veille


async def test_la_base_qui_tombe_a_la_recharge_ne_coupe_pas_la_piste(banc, adresse, pistes, db_session):
    import backend.database as db_module

    b = await banc()
    pl = await playlist(db_session, pistes[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="duree", fin_valeur=30, montee_s=0)

    def casse():
        raise ConnectionError("base indisponible")

    avant = db_module.async_session
    db_module.async_session = casse  # la recharge de la playlist échoue
    try:
        assert await b.fin() == "joue"  # la piste a joué, puis plus rien : veille
    finally:
        db_module.async_session = avant
    assert len(b.dmr.jouees) == 1 and b.telnet()[-1] == "PWSTANDBY"


async def test_arreter_pendant_l_attente_de_playing(banc, adresse, pistes):
    b = await banc(cadence=Cadence(**{**CADENCE.__dict__, "attente_play_s": 5.0}))
    b.dmr.demarrage_s = 30  # l'ampli reste en TRANSITIONING
    await b.lancer(fin_mode="pistes", fin_valeur=1, montee_s=0)
    await attendre(lambda: "Play" in b.dmr.actions(), delai=10)
    assert await b.seances.arreter() is True
    assert await b.fin() == "arretee"
    assert b.dmr.actions()[-1] == "Stop"
    assert "PWSTANDBY" not in b.telnet()


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
async def test_reprise_de_la_main_sans_mise_en_veille(banc, adresse, longues, db_session, geste):
    b = await banc()
    pl = await playlist(db_session, longues[:2])
    a, _ = await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING" and b.lien.etat["source"] == "NET", delai=10)
    await asyncio.sleep(0.8)  # au-delà de la fenêtre de grâce du changement de piste
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
    assert await b.fin() == "reprise_en_main"
    assert "PWSTANDBY" not in b.telnet()
    assert (await relire(b.session, a["id"]))["dernier_resultat"] == "reprise_en_main"


async def test_sans_duree_un_stop_pendant_que_reltime_avance_est_une_reprise(banc, adresse, longues, db_session):
    b = await banc()
    pl = await playlist(db_session, longues[2:3])  # TrackDuration NOT_IMPLEMENTED, pas de durée en base
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING", delai=10)
    await asyncio.sleep(0.9)  # quelques suivis : RelTime avance
    b.dmr.stop_externe()
    assert await b.fin() == "reprise_en_main"
    assert len(b.dmr.jouees) == 1


# ── une seule séance à la fois ──────────────────────────────────────────


async def test_une_alarme_remplace_la_seance_en_cours(banc, adresse, pistes, db_session):
    b = await banc()
    pl = await playlist(db_session, pistes[3:4])
    premiere, _ = await b.lancer(nom="Première", fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING", delai=10)
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
    # De son mieux : Stop, puis la veille par le lien encore connecté.
    assert b.dmr.actions()[-1] == "Stop"
    assert b.telnet()[-1] == "PWSTANDBY"
    await attendre(lambda: b.dmr.ouvertes == 0)
    assert not [t for t in asyncio.all_tasks() if t.get_name().startswith("denon:seance")]
    await attendre(lambda: not b.seances.en_vol, delai=5)  # rien d'écrit après le test


async def test_l_arret_d_unisson_tient_sous_8_s_meme_si_rien_ne_repond(banc, adresse, pistes):
    """Le cœur (≥ 0.5, #1068) n'accorde que 10 s aux tâches des plugins à
    l'arrêt. Avec les bornes d'arrêt de production, un lecteur qui ne répond
    plus (Stop pendu) et un lien bouché (la veille attend son créneau),
    `tourner` rend la main en moins de 8 s après l'annulation."""
    b = await banc(replace(CADENCE, arret_s=5.0, stop_arret_s=1.5, veille_arret_s=2.0, budget_arret_s=6.0, fermeture_s=0.5))
    await b.lancer(fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING")
    # Le lecteur se tait : toute requête SOAP attend une minute.
    b.dmr.attente = 60.0
    # Le lien se bouche : une commande part, et la suivante (la veille)
    # attend un créneau de 60 s, comme avec un ampli qui sature.
    b.lien.config = Config("127.0.0.1", b.ampli.port, 60.0)
    bouchon = asyncio.create_task(b.lien.envoyer("PW?"))
    await attendre(lambda: bouchon.done())

    debut = chrono.monotonic()
    b.superviseur.cancel()
    await asyncio.gather(b.superviseur, return_exceptions=True)
    duree = chrono.monotonic() - debut
    assert duree < 8.0, duree
    # Les deux gestes ont été tentés, chacun dans sa borne (1,5 s + 2 s).
    assert duree >= 3.0, duree
    assert "Stop" in [r.action for r in b.dmr.soaps]
    assert "PWSTANDBY" not in b.telnet()
    assert not b.seances.en_cours


async def test_le_resultat_s_ecrit_meme_annule_pendant_l_ecriture(banc, adresse, pistes, db_session, table):
    b = await banc(session=session_lente(table))
    pl = await playlist(db_session, pistes[:1])
    a, _ = await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="pistes", fin_valeur=1, montee_s=0)
    await attendre(lambda: (b.seances.derniere or {}).get("resultat") == "joue", delai=10)
    b.seances._tache.cancel()  # annulation tardive : l'écriture vient de commencer
    await asyncio.gather(b.seances._tache, return_exceptions=True)
    await attendre(lambda: not b.seances.en_vol, delai=5)
    assert (await relire(table, a["id"]))["dernier_resultat"] == "joue"


async def test_desactive_pendant_un_remplacement_rien_ne_demarre(banc, adresse, pistes, longues, db_session, table):
    b = await banc(session=session_lente(table))
    pl = await playlist(db_session, longues[:1])
    await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.dmr.etat == "PLAYING", delai=10)
    premiere = b.seances.courante
    seconde = asyncio.create_task(b.seances.lancer(await b.poser(nom="Seconde", fin_mode="pistes", fin_valeur=1)))
    # La première s'arrête (son résultat s'écrit lentement) : on désactive.
    await attendre(lambda: premiere.motif_arret == "remplacee", delai=10)
    b.superviseur.cancel()
    assert await seconde == "plugin_desactive"
    await asyncio.gather(b.superviseur, return_exceptions=True)
    assert not [t for t in asyncio.all_tasks() if t.get_name().startswith("denon:seance")]
    await attendre(lambda: not b.seances.en_vol, delai=5)  # rien d'écrit après le test


async def test_deux_annulations_de_suite_posent_quand_meme_l_etat_et_le_resultat(banc, adresse, longues, db_session, table):
    b = await banc()
    pl = await playlist(db_session, longues[:1])
    a, _ = await b.lancer(contexte="playlist", contexte_id=pl, fin_mode="sans_limite", fin_valeur=None, montee_s=0)
    await attendre(lambda: b.seances.courante is not None and b.seances.courante.etat == "lecture", delai=10)
    seance, tache = b.seances.courante, b.seances._tache
    b.dmr.attentes["POST"] = 0.6  # le Stop du ménage traîne
    seance.motif_arret = "arretee"
    tache.cancel()  # « Arrêter »…
    await asyncio.sleep(0.2)
    tache.cancel()  # … puis désactiver, pendant le Stop
    await asyncio.gather(tache, return_exceptions=True)
    assert (seance.etat, seance.resultat) == ("finie", "arretee")
    await attendre(lambda: "Stop" in b.dmr.actions(), delai=5)  # le ménage s'est poursuivi
    await attendre(lambda: not b.seances.en_vol, delai=10)
    assert (await relire(table, a["id"]))["dernier_resultat"] == "arretee"


async def test_le_lien_qui_meurt_coupe_la_seance_lien_mort_et_met_le_plugin_en_panne(
        client, table, faux_ampli, dmr, adresse, longues, db_session):
    """Par la vraie mécanique du cœur : `ctx.tache` et `sur_panne`."""
    faux_ampli.echo = True
    casse = []

    def config():
        if casse:
            raise RuntimeError("configuration illisible")
        return Config("127.0.0.1", faux_ampli.port, 0.01)

    ctx = contexte()
    lien = Lien(config, PILOTES["avrx4000"], attente_min=0.05, attente_max=0.2)
    lecteur = LecteurDlna(f"{dmr.base}/description.xml", delai=1)
    seances = Seances(ctx, lien, lecteur, table, fuseau=lambda: PARIS, delai_reveil_s=lambda: 0.05, cadence=CADENCE)
    pannes = []
    ctx.sur_panne = pannes.append
    ctx.tache(lambda: seances.tourner(lien.tourner))
    ctx.demarrer()
    try:
        await attendre(lambda: lien.connecte and lien.en_attente == 0, delai=5)
        pl = await playlist(db_session, longues[:1])
        async with table() as s:
            a = await alarmes.creer(s, alarmes.valider(alarme(contexte="playlist", contexte_id=pl, fin_mode="sans_limite",
                                                              fin_valeur=None, montee_s=0)), a_paris("2026-11-05T22:00"))
            await s.commit()
        assert await seances.lancer(a) == "en_cours"
        await attendre(lambda: seances.courante is not None and seances.courante.etat == "lecture", delai=10)
        casse.append(1)
        await faux_ampli.couper()  # le lien se reconnecte… et sa configuration lève
        await attendre(lambda: pannes, delai=10)
        assert "configuration illisible" in pannes[0]
        assert seances.derniere["resultat"] == "lien_mort"
        await attendre(lambda: not seances.en_vol, delai=10)
        assert (await relire(table, a["id"]))["dernier_resultat"] == "lien_mort"
    finally:
        ctx.annuler()
        await asyncio.sleep(0.1)


async def test_l_arret_attend_les_appels_nes_pendant_l_attente_et_journalise_les_abandons(banc, caplog):
    import logging

    from denon.backend.seance import _en_vol

    caplog.set_level(logging.WARNING, logger="unisson.plugin.denon")
    b = await banc()
    await asyncio.sleep(0.05)  # le superviseur a démarré
    fini = []

    async def tardif():
        await asyncio.sleep(0.3)
        fini.append("tardif")

    async def premier():
        await asyncio.sleep(0.2)
        _en_vol(b.seances.en_vol, tardif())  # naît pendant l'attente de l'arrêt

    async def interminable():
        await asyncio.sleep(3)

    _en_vol(b.seances.en_vol, premier())
    _en_vol(b.seances.en_vol, interminable())
    b.superviseur.cancel()
    await asyncio.gather(b.superviseur, return_exceptions=True)
    assert fini == ["tardif"]
    assert "abandonné" in caplog.text and "interminable" in caplog.text
