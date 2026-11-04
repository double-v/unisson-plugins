"""Les pilotes : ce qui est propre à un modèle d'ampli dans son protocole telnet.

Le lien (`lien.py`) ne connaît aucune commande ; un pilote valide une
commande, lit une trame, et encode les gestes (allumer, volume, source…).
Repris de `denon-api` (`server/drivers/avrx4000.js`), au comportement près.
"""

from __future__ import annotations

import math
import re

from unisson.plugin import Plafond

_COMMANDE = re.compile(r"[A-Z0-9? ]{1,32}")
_VOLUME = re.compile(r"\d{2,3}")
_SOURCE = re.compile(r"SI\S+")


def _arrondi(x: float) -> int:
    """`Math.round` de JavaScript (moitié vers +∞), pas l'arrondi bancaire."""
    return math.floor(x + 0.5)


def lire_volume(brut: str) -> float | None:
    """`MV45` → -35 dB ; `MV595` → -20,5 dB (trois chiffres : demi-dB)."""
    if not _VOLUME.fullmatch(brut):
        return None
    valeur = int(brut) / 10 if len(brut) == 3 else int(brut)
    db = _arrondi((valeur - 80) * 10) / 10
    return int(db) if db.is_integer() else db  # -35, pas -35.0, comme denon-api


class Avrx4000:
    id = "avrx4000"
    libelle = "Denon AVR-X4000"
    port_defaut = 23
    requetes_initiales = ("PW?", "MV?", "MU?", "SI?")

    # Le réveil (`seance.py`). Valeurs provisoires, **à confirmer en R0**
    # (recette sur l'ampli, `docs/reveil.md`) :
    # - la commande qui bascule sur la source réseau ; None : on n'en envoie
    #   aucune (l'ampli bascule seul quand on lui fait jouer un flux).
    #   Recette du 2026-11-02 : l'AVR-X4000 ne bascule PAS seul (il reste
    #   sur sa dernière entrée, le lecteur DLNA joue dans le vide). `SINET`
    #   collé à `Play` coupe la lecture (R0 du 2026-11-01), envoyé quelques
    #   secondes avant il tient : la séance l'envoie à l'allumage ;
    source_reseau: str | None = "SINET"
    # - le temps de sortie de veille avant que `Play` prenne (le réglage
    #   `delai_reveil_s` du plugin le remplace) ;
    delai_reveil_s: float = 8.0
    # - ce que l'ampli lit vraiment, mieux que ce qu'il annonce.
    plafond: Plafond | None = Plafond(frequence_max=96000, profondeur_max=24)

    def valider(self, commande: str) -> bool:
        return isinstance(commande, str) and bool(_COMMANDE.fullmatch(commande))

    def lire(self, etat: dict, ligne: str) -> bool:
        """Applique une trame à l'état ; rend False si elle ne le touche pas."""
        if ligne == "PWON":
            etat["power"] = True
        elif ligne.startswith("PWSTANDBY"):
            etat["power"] = False
        elif ligne in ("ZMON", "ZMOFF"):
            # La zone principale : `ZMOFF` sans `PWSTANDBY` quand une autre
            # zone joue encore. Le réveil la lit comme une mise en veille.
            etat["zone"] = ligne == "ZMON"
        elif ligne == "MUON":
            etat["mute"] = True
        elif ligne == "MUOFF":
            etat["mute"] = False
        elif ligne.startswith("MVMAX"):
            return False
        elif ligne.startswith("MV"):
            volume = lire_volume(ligne[2:])
            if volume is None:
                return False
            etat["volume"] = volume
        elif _SOURCE.fullmatch(ligne):
            etat["source"] = ligne[2:]
        else:
            return False
        return True

    def alimentation(self, allume: bool) -> str:
        return "PWON" if allume else "PWSTANDBY"

    def zone_principale(self, allume: bool) -> str:
        """Le réveil n'allume que la zone principale : `PWON` réveillerait
        aussi les zones 2 et 3, et `PWSTANDBY` couperait une zone 2 déjà en
        route. Sortie de veille, l'ampli pousse `PWON` puis `ZMON` ; `ZMOFF`
        le remet en veille (il pousse `PWSTANDBY`) si aucune autre zone ne
        joue."""
        return "ZMON" if allume else "ZMOFF"

    def sourdine(self, muet: bool) -> str:
        return "MUON" if muet else "MUOFF"

    def source(self, source: str) -> str:
        return f"SI{source}"

    def volume(self, db: float) -> str:
        return f"MV{_arrondi((db + 80) * 10):03d}"

    def est_source_reseau(self, source: str | None) -> bool:
        """La source de l'état (`NET` après `SINET`) est-elle la source réseau ?"""
        return self.source_reseau is not None and source == self.source_reseau.removeprefix("SI")

    def volume_plus(self) -> str:
        return "MVUP"

    def volume_moins(self) -> str:
        return "MVDOWN"


PILOTES = {"avrx4000": Avrx4000()}
