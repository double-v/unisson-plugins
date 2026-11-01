"""Les pilotes : ce qui est propre à un modèle d'ampli dans son protocole telnet.

Le lien (`lien.py`) ne connaît aucune commande ; un pilote valide une
commande, lit une trame, et encode les gestes (allumer, volume, source…).
Repris de `denon-api` (`server/drivers/avrx4000.js`), au comportement près.
"""

from __future__ import annotations

import math
import re

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

    def valider(self, commande: str) -> bool:
        return isinstance(commande, str) and bool(_COMMANDE.fullmatch(commande))

    def lire(self, etat: dict, ligne: str) -> bool:
        """Applique une trame à l'état ; rend False si elle ne le touche pas."""
        if ligne == "PWON":
            etat["power"] = True
        elif ligne.startswith("PWSTANDBY"):
            etat["power"] = False
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

    def sourdine(self, muet: bool) -> str:
        return "MUON" if muet else "MUOFF"

    def source(self, source: str) -> str:
        return f"SI{source}"

    def volume(self, db: float) -> str:
        return f"MV{_arrondi((db + 80) * 10):03d}"

    def volume_plus(self) -> str:
        return "MVUP"

    def volume_moins(self) -> str:
        return "MVDOWN"


PILOTES = {"avrx4000": Avrx4000()}
