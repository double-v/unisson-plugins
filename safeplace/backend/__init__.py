"""Safeplace — plugin officiel d'exemple (spec 018, US6).

Signaler un artiste est un choix personnel : la fonction vit donc hors du
cœur, inactive par défaut. Le plugin montre les gestes d'un plugin complet :
des routes, une table à lui (adoptée si elle existe déjà), un outil de
l'assistant, un type d'opération qu'il propose en carte dans le chat
(`safeplace.signaler`), des écrans aux emplacements de la fiche artiste et
du chat, et l'**usage**
d'une opération du cœur (`trash_artist`, provenance `safeplace`) qu'il ne
possède pas.
"""

from unisson.plugin import Contexte

from . import operation, outils, routes


def enregistrer(ctx: Contexte) -> None:
    ctx.routeur(routes.brancher(ctx))
    ctx.outil_chat(outils.VERIFIER, outils.fabriquer(ctx))
    ctx.type_operation(operation.fabriquer(ctx))
