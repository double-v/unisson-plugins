"""Les routes du réveil, sous `/api/plugins/denon/reveil/`, protégées par le
même jeton que l'API de denon-api (conception : `docs/reveil.md`).

Les alarmes, le testeur de fuseau et l'horloge (lot 3) ; la séance :
`essayer`, `seance`, `arreter` et le `diagnostic` (lot 4). Ces routes ne
sont pas servies par l'écoute à part (`port_ecoute`) : elle ne sert que
l'API de denon-api, pour Hublot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import JSONResponse
from unisson.plugin import AdresseReseauNonReglee

from . import alarmes
from .alarmes import ID_MAX, UTC, FuseauRegle, Invalide
from .dlna import ErreurDlna
from .ordonnanceur import Ordonnanceur, echeance_de_test
from .routes import _Route, corps, garde_du_jeton
from .seance import Seances

# L'admin est servie sous `/admin` : le lien du réglage s'y préfixe.
PREFIXE_ADMIN = "/admin"
CONSEILS = [
    {
        "code": "controle_reseau",
        "message": "Sur l'ampli, réglez « Contrôle réseau » sur « Toujours activé » (Réseau › Paramètres) : "
                   "sans lui, il ne répond plus en veille, ni en telnet ni en UPnP, et le réveil ne peut pas l'allumer.",
    },
    {
        "code": "ip_fixe",
        "message": "Donnez une adresse IP fixe à l'ampli (bail réservé sur la box) : le réveil le joint à l'adresse réglée.",
    },
]

DELAIS_DE_TEST = (5, 10)
# Le testeur sans alarme modèle : un tirage de la bibliothèque, volume bas,
# fin après une piste.
_TEST_PAR_DEFAUT = {
    "contexte": "bibliotheque",
    "volume_depart_db": -50.0,
    "volume_cible_db": -50.0,
    "montee_s": 0,
}


def horloge(fz: ZoneInfo, maintenant: datetime, avertissement: str | None = None) -> dict:
    return {
        "fuseau": fz.key,
        "local": alarmes.local(maintenant, fz),
        "decalage": alarmes.decalage(maintenant, fz),
        "utc": maintenant.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        # Le réglage `fuseau` est invalide : le réveil reste sur le dernier bon.
        "avertissement": avertissement,
    }


def _refus(e: Invalide) -> JSONResponse:
    return JSONResponse({"error": "alarme_invalide", "erreurs": e.erreurs}, status_code=422)


_INTROUVABLE = {"error": "alarme_introuvable"}
# Un identifiant de chemin au-delà d'un INTEGER de Postgres : 422, pas 500.
Ident = Annotated[int, Path(ge=1, le=ID_MAX)]


def fabriquer(
    ordo: Ordonnanceur,
    session: Callable,
    fuseau: FuseauRegle,
    jeton: Callable[[], str],
    *,
    seances: Seances | None = None,
    adresse_reseau: Callable[[], str] | None = None,
) -> APIRouter:
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
                alarme = await alarmes.modifier(s, ident, valeurs, ordo.maintenant(), avant)
            await s.commit()
        ordo.reveiller()
        return JSONResponse(vue(alarme), status_code=201 if ident is None else 200)

    @router.get("/alarmes")
    async def lister():
        async with session() as s:
            toutes = await alarmes.lister(s)
        # Une alarme de test passée est finie, même si sa suppression n'est
        # pas encore écrite : son résultat se lit par `/tester/{id}`.
        restantes = [a for a in toutes if a["id"] not in ordo.tests and not (a["test"] and not a["active"])]
        fz = fuseau()
        return {"fuseau": fz.key, "avertissement": fuseau.avertissement, "alarmes": [vue(a) for a in restantes]}

    @router.post("/alarmes")
    async def creer(request: Request):
        return await enregistrer(await corps(request))

    @router.put("/alarmes/{ident}")
    async def modifier(request: Request, ident: Ident):
        return await enregistrer(await corps(request), ident)

    @router.delete("/alarmes/{ident}")
    async def supprimer(ident: Ident):
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
        if modele_id is not None and not alarmes.identifiant(modele_id):
            erreurs.append({"champ": "alarme_id", "message": "identifiant d'alarme attendu"})
        if erreurs:
            return _refus(Invalide(erreurs))
        fz = fuseau()
        maintenant = ordo.maintenant()
        echeance = echeance_de_test(maintenant, dans_s)
        heure = echeance.astimezone(fz).strftime("%H:%M:%S")
        # Pendant l'heure en double du retour à l'heure d'hiver, une heure
        # locale désigne d'abord le premier passage : l'alarme partirait le
        # lendemain, pas à l'échéance annoncée.
        if alarmes.prochaine_occurrence(fz, alarmes.lire_heure(heure), 0, maintenant) != echeance:
            return _refus(Invalide([{
                "champ": "dans_s",
                "message": f"{heure} existe deux fois aujourd'hui (changement d'heure) : "
                           "réessayer après l'heure en double",
            }]))
        async with session() as s:
            modele = await alarmes.lire(s, modele_id) if modele_id is not None else await alarmes.premiere(s)
            if modele_id is not None and modele is None:
                return JSONResponse(_INTROUVABLE, status_code=404)
            # Le contexte et les volumes du modèle ; la fin, toujours courte.
            reglages = {k: modele[k] for k in alarmes.DEFAUTS} if modele else dict(_TEST_PAR_DEFAUT)
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
                "horloge": horloge(fz, maintenant, fuseau.avertissement),
                "echeance": alarmes.local(echeance, fz),
                "echeance_utc": echeance.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            },
            status_code=201,
        )

    @router.get("/tester/{ident}")
    async def resultat_test(ident: Ident):
        """Où en est une alarme de test : `en_attente`, puis `partie` (avec
        son départ et son retard) ou `manquee`, même une fois supprimée."""
        resultat = await ordo.resultat_test(ident)
        if resultat is None:
            return JSONResponse(_INTROUVABLE, status_code=404)
        return resultat

    @router.get("/horloge")
    async def heure_du_serveur():
        fz = fuseau()
        return horloge(fz, ordo.maintenant(), fuseau.avertissement)

    if seances is not None:
        _routes_de_la_seance(router, seances, ordo, session, fuseau, adresse_reseau)
    return router


def _reseau(adresse_reseau: Callable[[], str] | None) -> dict:
    lien = PREFIXE_ADMIN + AdresseReseauNonReglee.reglage
    try:
        adresse = adresse_reseau() if adresse_reseau else None
    except AdresseReseauNonReglee as e:
        return {"reglee": False, "adresse": None, "reglage": lien, "message": e.libelle}
    return {"reglee": adresse is not None, "adresse": adresse, "reglage": lien, "message": None}


def _routes_de_la_seance(router: APIRouter, seances: Seances, ordo: Ordonnanceur, session: Callable,
                         fuseau: FuseauRegle, adresse_reseau: Callable[[], str] | None) -> None:
    @router.post("/alarmes/{ident}/essayer")
    async def essayer(ident: Ident):
        """La séance de cette alarme, tout de suite (elle remplace celle en
        cours). 202 si elle tourne ; 409 avec le code si elle ne peut pas
        partir (rien n'a été envoyé à l'ampli)."""
        async with session() as s:
            alarme = await alarmes.lire(s, ident)
        if alarme is None:
            return JSONResponse(_INTROUVABLE, status_code=404)
        code = await seances.lancer(alarme, ecrire=True)
        if code != "en_cours":
            corps_ = {"error": code, "message": (seances.derniere or {}).get("message") or code}
            if code == AdresseReseauNonReglee.code:
                corps_["reglage"] = PREFIXE_ADMIN + AdresseReseauNonReglee.reglage
            return JSONResponse(corps_, status_code=409)
        return JSONResponse({"resultat": code, **seances.vue()}, status_code=202)

    @router.get("/seance")
    async def seance():
        """`{seance, derniere}` : la séance en cours (null sinon) et la
        dernière finie, avec son résultat."""
        return seances.vue()

    @router.post("/seance/arreter")
    async def arreter():
        """Arrête la séance en cours (`Stop`), sans mettre l'ampli en veille."""
        arretee = await seances.arreter()
        return {"arretee": arretee, **seances.vue()}

    @router.get("/diagnostic")
    async def diagnostic():
        lien = seances.lien
        pilote = lien.pilote
        telnet = {
            "connecte": lien.connecte,
            "hote": lien.config.hote or None,
            "port": lien.config.port,
            "alimentation": lien.etat["power"],
            "source": lien.etat["source"],
            "volume": lien.etat["volume"],
        }
        upnp: dict = {"joignable": False, "description": None, "formats": [], "erreur": None}
        try:
            upnp["description"] = seances.lecteur.adresse()
        except Exception as e:  # noqa: BLE001 — réglage vide ou illisible
            upnp["erreur"] = str(e)
        if upnp["description"]:
            try:
                upnp["formats"] = await seances.lecteur.protocoles()
                upnp["joignable"] = True
            except ErreurDlna as e:
                upnp["erreur"] = str(e)
        reseau = _reseau(adresse_reseau)
        problemes = []
        if not telnet["connecte"]:
            problemes.append("telnet_deconnecte")
        if not upnp["joignable"]:
            problemes.append("upnp_injoignable")
        if not reseau["reglee"]:
            problemes.append("adresse_reseau_non_reglee")
        if fuseau.avertissement:
            problemes.append("fuseau_invalide")
        fz = fuseau()
        plafond = pilote.plafond
        return {
            "ok": not problemes,
            "problemes": problemes,
            "telnet": telnet,
            "upnp": upnp,
            "adresse_reseau": reseau,
            "pilote": {
                "id": pilote.id,
                "libelle": pilote.libelle,
                "source_reseau": pilote.source_reseau,
                "delai_reveil_s": seances.delai(),
                "plafond": {"frequence_max": plafond.frequence_max, "profondeur_max": plafond.profondeur_max} if plafond else None,
            },
            "conseils": CONSEILS,
            "horloge": horloge(fz, ordo.maintenant(), fuseau.avertissement),
            "seance": seances.vue()["seance"],
        }
