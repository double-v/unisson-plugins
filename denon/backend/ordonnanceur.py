"""L'ordonnanceur du réveil : la tâche de fond qui fait partir les alarmes.

Il dort jusqu'à la prochaine échéance (30 s au plus) ; toute écriture
d'alarme le réveille aussitôt (`reveiller()`). La précision visée est
d'environ une seconde, pour que le testeur de 5 s ait un sens.

Au départ, il note l'occurrence traitée **avant** d'appeler l'accroche
(`alarmes.prendre`, une écriture conditionnelle) : une alarme ne part
jamais deux fois, même après un redémarrage ou une réactivation du plugin.
L'accroche `declencher(alarme)` rend le code qui va dans `dernier_resultat` ;
elle doit rendre la main vite (la séance du lot 4 tournera à côté).

L'horloge (`maintenant`) est injectable : les tests appellent `passer()`
avec une horloge fixée.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from . import alarmes

SOMMEIL_MAX_S = 30
REPRISE_S = 1  # après un passage en échec, on réessaie vite : une alarme attend
_TESTS_GARDES = 20

Declencher = Callable[[dict], Awaitable[str | None]]


def maintenant_utc() -> datetime:
    return datetime.now(timezone.utc)


def accroche_par_defaut(journal: logging.Logger) -> Declencher:
    """Lot 3 : pas encore de séance. Le départ est journalisé, c'est tout."""

    async def declencher(alarme: dict) -> str:
        journal.info("alarme %s « %s » déclenchée (%s)", alarme["id"], alarme["nom"], alarme["heure"])
        return "declenchee"

    return declencher


class Ordonnanceur:
    def __init__(
        self,
        session: Callable,
        fuseau: Callable[[], ZoneInfo],
        *,
        declencher: Declencher | None = None,
        maintenant: Callable[[], datetime] = maintenant_utc,
        journal: logging.Logger | None = None,
    ):
        self.session = session
        self.fuseau = fuseau
        self.journal = journal or logging.getLogger("unisson.plugin.denon")
        self.declencher = declencher or accroche_par_defaut(self.journal)
        self.maintenant = maintenant
        self._evenement = asyncio.Event()
        # Le résultat des alarmes de test, lisible après leur suppression.
        self.tests: OrderedDict[int, dict] = OrderedDict()

    def reveiller(self) -> None:
        """Une alarme vient d'être écrite : on recalcule tout de suite."""
        self._evenement.set()

    async def tourner(self) -> None:
        nettoye = False
        while True:
            self._evenement.clear()
            try:
                if not nettoye:
                    await self.nettoyer()
                    nettoye = True
                prochaine = await self.passer()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Base indisponible : on réessaie dans une seconde, sans
                # mettre le plugin en panne (le lien doit vivre).
                self.journal.exception("ordonnanceur du réveil : passage en échec")
                prochaine = self.maintenant() + timedelta(seconds=REPRISE_S)
            attente = SOMMEIL_MAX_S
            if prochaine is not None:
                attente = min(max((prochaine - self.maintenant()).total_seconds(), 0), SOMMEIL_MAX_S)
            try:
                await asyncio.wait_for(self._evenement.wait(), attente)
            except TimeoutError:
                pass

    async def nettoyer(self) -> None:
        """Au démarrage : les alarmes de test passées qu'un arrêt a laissées
        entre leur départ et leur suppression."""
        async with self.session() as s:
            n = await alarmes.supprimer_tests_finis(s)
            await s.commit()
        if n:
            self.journal.info("réveil : %d alarme(s) de test passée(s) supprimée(s)", n)

    async def passer(self) -> datetime | None:
        """Fait partir ce qui est dû, note ce qui est manqué ; rend la
        prochaine échéance (UTC), ou None s'il n'y en a aucune."""
        fz = self.fuseau()
        maintenant = self.maintenant()
        async with self.session() as s:
            actives = await alarmes.lister(s, actives=True)
        prochaine = None
        for alarme in actives:
            etat, occ = alarmes.occurrence(alarme, fz, maintenant)
            if etat == "attendre":
                if occ is not None and (prochaine is None or occ < prochaine):
                    prochaine = occ
            elif etat == "partir":
                await self._partir(alarme, occ)
                prochaine = maintenant  # sa suivante se calcule au passage d'après
            elif etat == "manquee":
                await self._manquer(alarme, occ, maintenant)
                prochaine = maintenant
        return prochaine

    async def _partir(self, alarme: dict, occ: datetime) -> None:
        depart = self.maintenant()
        async with self.session() as s:
            prise = await alarmes.prendre(s, alarme["id"], occ, lu=alarme["arme_le"], execution=depart, resultat="en_cours")
            await s.commit()
        if prise is None:
            return  # un autre passage l'a déjà fait partir
        retard = (depart - occ).total_seconds()
        if retard > 1:
            self.journal.warning("alarme %s partie avec %.1f s de retard", alarme["id"], retard)
        try:
            resultat = await self.declencher(prise) or "declenchee"
        except Exception as e:
            self.journal.exception("alarme %s : l'accroche a échoué", alarme["id"])
            resultat = f"erreur:{type(e).__name__}"
        resultat = str(resultat)[: alarmes.RESULTAT_MAX]
        prise["dernier_resultat"] = resultat
        async with self.session() as s:
            await alarmes.noter_resultat(s, prise["id"], resultat)
            await s.commit()
        await self._fin_de_test(prise)

    async def _manquer(self, alarme: dict, occ: datetime, maintenant: datetime) -> None:
        async with self.session() as s:
            prise = await alarmes.prendre(s, alarme["id"], occ, lu=alarme["arme_le"], execution=None, resultat="manquee")
            await s.commit()
        if prise is None:
            return
        self.journal.warning(
            "alarme %s « %s » manquée : échéance %s, plus de %d min de retard",
            alarme["id"], alarme["nom"], alarmes.iso(occ), alarmes.RATTRAPAGE.seconds // 60,
        )
        await self._fin_de_test(prise)

    def _resume(self, alarme: dict) -> dict:
        """Le résultat d'une alarme de test prise : partie (son départ et son
        retard) ou manquée."""
        fz = self.fuseau()
        retard = alarmes.retard_ms(alarme)
        partie = retard is not None
        return {
            "id": alarme["id"],
            "nom": alarme["nom"],
            "etat": "partie" if partie else "manquee",
            "echeance": alarmes.local(alarmes.lire_iso(alarme["derniere_echeance"]), fz),
            "depart": alarmes.local(alarmes.lire_iso(alarme["derniere_execution"]), fz) if partie else None,
            "retard_ms": retard,
            "dernier_resultat": alarme["dernier_resultat"],
        }

    async def _fin_de_test(self, alarme: dict) -> None:
        """L'alarme de test se supprime après son passage ; son résultat
        reste lisible (`resultat_test`)."""
        if not alarme["test"]:
            return
        self.tests[alarme["id"]] = self._resume(alarme)
        while len(self.tests) > _TESTS_GARDES:
            self.tests.popitem(last=False)
        async with self.session() as s:
            await alarmes.supprimer(s, alarme["id"])
            await s.commit()

    async def resultat_test(self, ident: int) -> dict | None:
        if ident in self.tests:
            return self.tests[ident]
        async with self.session() as s:
            alarme = await alarmes.lire(s, ident)
        if alarme is None or not alarme["test"]:
            return None
        if not alarme["active"]:
            # Prise mais pas encore supprimée (unisson arrêté entre les deux).
            return self._resume(alarme)
        fz = self.fuseau()
        _, occ = alarmes.occurrence(alarme, fz, self.maintenant())
        return {"id": ident, "nom": alarme["nom"], "etat": "en_attente", "echeance": alarmes.local(occ, fz),
                "depart": None, "retard_ms": None, "dernier_resultat": None}


def echeance_de_test(maintenant: datetime, dans_s: int) -> datetime:
    """Maintenant plus `dans_s`, arrondi à la seconde **suivante** : l'heure
    d'une alarme n'a pas de fraction, et l'arrondi inférieur la ferait partir
    avant le délai annoncé."""
    cible = maintenant + timedelta(seconds=dans_s)
    if cible.microsecond:
        cible = cible.replace(microsecond=0) + timedelta(seconds=1)
    return cible
