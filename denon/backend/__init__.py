"""Denon — plugin officiel (spec 023 d'unisson, #343).

Premier lot : le **multiplexeur** qui remplace le conteneur `denon-api`.
Une connexion telnet unique vers l'ampli, partagée par unisson, Hublot et
les autres, derrière la même API HTTP que `denon-api` :

- sous `/api/plugins/denon/` (`http://<unisson>/api/plugins/denon/api/state`) ;
- et, si `port_ecoute` est réglé, seule sur ce port, à l'adresse exacte de
  l'ancien conteneur (`http://<nas>:8100/api/state`).

Le réveil (`docs/reveil.md`) s'y ajoute : les alarmes et leur ordonnanceur
(`alarmes.py`, `ordonnanceur.py`), la séance qui joue la musique par UPnP
(`seance.py`, `dlna.py`), et leurs routes sous `/reveil/`.
"""

from unisson.plugin import Contexte

from . import alarmes, dlna, ecoute, reveil, routes
from .lien import Config, Lien
from .ordonnanceur import Ordonnanceur
from .pilotes import PILOTES
from .seance import Seances


def adresse_upnp(hote_upnp: str, hote: str) -> str:
    """L'adresse de la description UPnP : `hote_upnp` (un hôte, ou une URL
    complète), sinon l'hôte telnet, sur le port 8080."""
    hote_upnp = hote_upnp.strip()
    if "://" in hote_upnp:
        return hote_upnp
    if not (choisi := hote_upnp or hote.strip()):
        raise ValueError("ni hote_upnp ni hote ne sont réglés")
    return dlna.adresse_description(choisi)


def enregistrer(ctx: Contexte) -> None:
    pilote = PILOTES.get(ctx.reglage("pilote"))
    if pilote is None:
        raise ValueError(f"pilote Denon inconnu : {ctx.reglage('pilote')!r} (connus : {', '.join(PILOTES)})")

    def config() -> Config:
        return Config(
            hote=ctx.reglage("hote").strip(),
            port=ctx.reglage("port_telnet") or pilote.port_defaut,
            cadence_s=max(ctx.reglage("cadence_ms"), 0) / 1000,
        )

    def delai_reveil() -> float:
        # Vide : celui du pilote (à mesurer en R0) ; illisible : idem.
        brut = ctx.reglage("delai_reveil_s").strip()
        try:
            return max(0.0, float(brut)) if brut else pilote.delai_reveil_s
        except ValueError:
            ctx.journal.warning("réglage delai_reveil_s illisible (%r) : %g s", brut, pilote.delai_reveil_s)
            return pilote.delai_reveil_s

    # Vérifié à l'activation (un fuseau inconnu la refuse), puis relu à chaque
    # usage ; un réglage invalide posé à chaud garde le dernier bon fuseau.
    fuseau = alarmes.FuseauRegle(lambda: ctx.reglage("fuseau"), ctx.journal)
    fuseau.valide = alarmes.fuseau(ctx.reglage("fuseau"))

    lien = Lien(config, pilote, journal=ctx.journal)
    ctx.routeur(routes.fabriquer(lien, lambda: ctx.secret("jeton")))
    ctx.tache(lien.tourner)

    # Relue à chaque appel : changer d'hôte prend effet à chaud.
    lecteur = dlna.LecteurDlna(lambda: adresse_upnp(ctx.reglage("hote_upnp"), ctx.reglage("hote")))
    ordonnanceur = Ordonnanceur(ctx.session, fuseau, journal=ctx.journal)
    seances = Seances(ctx, lien, lecteur, ctx.session, fuseau=fuseau, delai_reveil_s=delai_reveil,
                      ordonnanceur=ordonnanceur, journal=ctx.journal)
    ordonnanceur.declencher = seances.declencher
    ctx.routeur(reveil.fabriquer(ordonnanceur, ctx.session, fuseau, lambda: ctx.secret("jeton"),
                                 seances=seances, adresse_reseau=ctx.adresse_reseau))
    ctx.tache(ordonnanceur.tourner)
    ctx.tache(seances.tourner)
    # Le port est lu à l'activation : le changer demande de réactiver le plugin.
    if port := ctx.reglage("port_ecoute"):
        seul = routes.fabriquer(lien, lambda: ctx.secret("jeton"))
        ctx.tache(lambda: ecoute.servir(seul, port, ctx.journal))
