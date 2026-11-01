"""Les routes du réveil, sous `/api/plugins/denon/reveil/`, protégées par le
même jeton que l'API de denon-api (conception : `docs/reveil.md`).

Lot 3 : les alarmes, le testeur de fuseau et l'horloge. `essayer`, `seance`
et `diagnostic` viendront avec la séance (lot 4). Ces routes ne sont pas
servies par l'écoute à part (`port_ecoute`) : elle ne sert que l'API de
denon-api, pour Hublot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from . import alarmes
from .alarmes import UTC, Invalide
from .ordonnanceur import Ordonnanceur, echeance_de_test
from .routes import _Route, corps, garde_du_jeton

DELAIS_DE_TEST = (5, 10)
# Le testeur sans alarme modèle : un tirage de la bibliothèque, volume bas,
# fin après une piste.
_TEST_PAR_DEFAUT = {
    "contexte": "bibliotheque",
    "volume_depart_db": -50.0,
    "volume_cible_db": -50.0,
    "montee_s": 0,
}


def horloge(fz: ZoneInfo, maintenant: datetime) -> dict:
    return {
        "fuseau": fz.key,
        "local": alarmes.local(maintenant, fz),
        "decalage": alarmes.decalage(maintenant, fz),
        "utc": maintenant.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def _refus(e: Invalide) -> JSONResponse:
    return JSONResponse({"error": "alarme_invalide", "erreurs": e.erreurs}, status_code=422)


_INTROUVABLE = {"error": "alarme_introuvable"}


def fabriquer(ordo: Ordonnanceur, session: Callable, fuseau: Callable[[], ZoneInfo], jeton: Callable[[], str]) -> APIRouter:
    router = APIRouter(prefix="/reveil", route_class=_Route, dependencies=[Depends(garde_du_jeton(jeton))])

    def vue(alarme: dict) -> dict:
        return alarmes.vue(alarme, fuseau(), ordo.maintenant())

    async def enregistrer(donnees: dict, ident: int | None = None):
        async with session() as s:
            avant = None
            if ident is not None:
                avant = await alarmes.lire(s, ident)
                if avant is None:
                    return JSONResponse(_INTROUVABLE, status_code=404)
            try:
                valeurs = alarmes.valider(donnees, avant)
                await alarmes.verifier_references(s, valeurs)
            except Invalide as e:
                return _refus(e)
            if ident is None:
                alarme = await alarmes.creer(s, valeurs, ordo.maintenant())
            else:
                alarme = await alarmes.modifier(s, ident, valeurs, ordo.maintenant())
            await s.commit()
        ordo.reveiller()
        return JSONResponse(vue(alarme), status_code=201 if ident is None else 200)

    @router.get("/alarmes")
    async def lister():
        async with session() as s:
            toutes = await alarmes.lister(s)
        # Une alarme de test passée est finie, même si sa suppression n'est
        # pas encore écrite : son résultat se lit par `/tester/{id}`.
        return {"fuseau": fuseau().key, "alarmes": [vue(a) for a in toutes if a["id"] not in ordo.tests]}

    @router.post("/alarmes")
    async def creer(request: Request):
        return await enregistrer(await corps(request))

    @router.put("/alarmes/{ident}")
    async def modifier(ident: int, request: Request):
        return await enregistrer(await corps(request), ident)

    @router.delete("/alarmes/{ident}")
    async def supprimer(ident: int):
        async with session() as s:
            trouvee = await alarmes.supprimer(s, ident)
            await s.commit()
        if not trouvee:
            return JSONResponse(_INTROUVABLE, status_code=404)
        ordo.reveiller()
        return Response(status_code=204)

    @router.post("/tester")
    async def tester(request: Request):
        """Une alarme unique dans 5 ou 10 s, passée par le vrai ordonnanceur :
        si elle part à l'heure, le fuseau et l'horloge sont bons."""
        donnees = await corps(request)
        dans_s, modele_id = donnees.get("dans_s"), donnees.get("alarme_id")
        erreurs = []
        if dans_s not in DELAIS_DE_TEST or isinstance(dans_s, bool):
            erreurs.append({"champ": "dans_s", "message": "5 ou 10 attendu"})
        if modele_id is not None and (not isinstance(modele_id, int) or isinstance(modele_id, bool)):
            erreurs.append({"champ": "alarme_id", "message": "identifiant d'alarme attendu"})
        if erreurs:
            return _refus(Invalide(erreurs))
        fz = fuseau()
        maintenant = ordo.maintenant()
        echeance = echeance_de_test(maintenant, dans_s)
        async with session() as s:
            modele = await alarmes.lire(s, modele_id) if modele_id is not None else await alarmes.premiere(s)
            if modele_id is not None and modele is None:
                return JSONResponse(_INTROUVABLE, status_code=404)
            # Le contexte et les volumes du modèle ; la fin, toujours courte.
            reglages = {k: modele[k] for k in alarmes.DEFAUTS} if modele else dict(_TEST_PAR_DEFAUT)
            heure = echeance.astimezone(fz).strftime("%H:%M:%S")
            reglages.update(nom=f"Test {heure}", active=True, heure=heure, jours=0, fin_mode="pistes", fin_valeur=1)
            try:
                valeurs = alarmes.valider(reglages)
                await alarmes.verifier_references(s, valeurs)
            except Invalide as e:
                return _refus(e)
            alarme = await alarmes.creer(s, valeurs, maintenant, test=True)
            await s.commit()
        ordo.reveiller()
        return JSONResponse(
            {
                "alarme": vue(alarme),
                "horloge": horloge(fz, maintenant),
                "echeance": alarmes.local(echeance, fz),
                "echeance_utc": echeance.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            },
            status_code=201,
        )

    @router.get("/tester/{ident}")
    async def resultat_test(ident: int):
        """Où en est une alarme de test : `en_attente`, puis `partie` (avec
        son départ et son retard) ou `manquee`, même une fois supprimée."""
        resultat = await ordo.resultat_test(ident)
        if resultat is None:
            return JSONResponse(_INTROUVABLE, status_code=404)
        return resultat

    @router.get("/horloge")
    async def heure_du_serveur():
        return horloge(fuseau(), ordo.maintenant())

    return router
