"""Convertir en MP3 tagué les pistes qu'unisson ne sait pas taguer (#950).

Un WMA à 192 kbps sans tags vaut moins qu'un MP3 au même débit qu'on peut
nommer, taguer et retrouver : ce plugin réencode les WMA avec perte d'un
album en MP3 (LAME, CBR au premier palier au moins égal à la source),
recopie leurs tags ASF en ID3v2.4, puis laisse le cœur poser les MP3 et
mettre les WMA à la corbeille (`ctx.remplacer_pistes`, cœur ≥ 0.8). Tout
passe par le tampon et le mode édition, et se révoque.
"""

from unisson.plugin import Contexte, TypeOperation

from . import service
from .routes import router


def enregistrer(ctx: Contexte) -> None:
    service._ctx["ctx"] = ctx
    ctx.routeur(router)
    ctx.type_operation(TypeOperation(
        "convertir.mp3", service.appliquer, service.annuler, service.verifier,
        # Un encodage d'album prend des minutes : jamais d'envoi automatique,
        # l'opérateur l'approuve au tampon.
        envoi_auto=False,
        type_cible="album",
    ))
