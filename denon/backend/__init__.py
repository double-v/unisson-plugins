"""Denon — plugin officiel (spec 023 d'unisson, #343).

Premier lot : le **multiplexeur** qui remplace le conteneur `denon-api`.
Une connexion telnet unique vers l'ampli, partagée par unisson, Hublot et
les autres, derrière la même API HTTP que `denon-api` :

- sous `/api/plugins/denon/` (`http://<unisson>/api/plugins/denon/api/state`) ;
- et, si `port_ecoute` est réglé, seule sur ce port, à l'adresse exacte de
  l'ancien conteneur (`http://<nas>:8100/api/state`).

Le réveil (`docs/reveil.md`) s'y ajoute : les alarmes et leur ordonnanceur
(lot 3, `alarmes.py`, `ordonnanceur.py`, routes sous `/reveil/`). La séance
(lecture UPnP) viendra au lot 4, par l'accroche `declencher`.
"""

from unisson.plugin import Contexte

from . import alarmes, ecoute, reveil, routes
from .lien import Config, Lien
from .ordonnanceur import Ordonnanceur
from .pilotes import PILOTES


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

    # Vérifié à l'activation (un fuseau inconnu la refuse), puis relu à chaque
    # usage ; un réglage invalide posé à chaud garde le dernier bon fuseau.
    fuseau = alarmes.FuseauRegle(lambda: ctx.reglage("fuseau"), ctx.journal)
    fuseau.valide = alarmes.fuseau(ctx.reglage("fuseau"))

    lien = Lien(config, pilote, journal=ctx.journal)
    ctx.routeur(routes.fabriquer(lien, lambda: ctx.secret("jeton")))
    ctx.tache(lien.tourner)

    ordonnanceur = Ordonnanceur(ctx.session, fuseau, journal=ctx.journal)
    ctx.routeur(reveil.fabriquer(ordonnanceur, ctx.session, fuseau, lambda: ctx.secret("jeton")))
    ctx.tache(ordonnanceur.tourner)
    # Le port est lu à l'activation : le changer demande de réactiver le plugin.
    if port := ctx.reglage("port_ecoute"):
        seul = routes.fabriquer(lien, lambda: ctx.secret("jeton"))
        ctx.tache(lambda: ecoute.servir(seul, port, ctx.journal))
