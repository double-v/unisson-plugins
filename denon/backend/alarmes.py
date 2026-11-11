"""Les alarmes du réveil : le modèle, sa validation, la prochaine occurrence.

Conception : `docs/reveil.md`. Une ligne par alarme dans
`plugin_denon.alarmes`. Les instants sont stockés en chaînes ISO, **en UTC
et toujours au même format** (`iso()`) : comparer deux chaînes compare deux
instants, en SQL comme en Python. L'heure d'une alarme, elle, est une heure
locale, dans le fuseau réglé.

Le plugin lit les tables du cœur (`playlists`, `artists`, `albums`,
`libraries`, ex-`genres` avant le cœur 0.10) en SQL, sans leurs modèles : la lecture est libre.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

TABLE = "plugin_denon.alarmes"
UTC = timezone.utc

CONTEXTES = ("playlist", "bibliotheque", "artiste", "album")
FINS = ("duree", "pistes", "sans_limite")
# Jusqu'à 10 minutes de retard (unisson redémarre), l'alarme part ; au-delà,
# elle est `manquee` et ne part pas.
RATTRAPAGE = timedelta(minutes=10)
# Les playlists dynamiques du cœur (`GET /api/playlists`) : calculées, sans
# ligne dans `playlists`. La façade les lit depuis le cœur 0.7 (unisson#1077).
PLAYLIST_ALBUMS_FAVORIS = -1
PLAYLIST_PISTES_FAVORITES = -2
PLAYLISTS_DYNAMIQUES = (PLAYLIST_ALBUMS_FAVORIS, PLAYLIST_PISTES_FAVORITES)
# Plus loin en arrière, tout est manqué : inutile de dérouler les jours.
_HORIZON = timedelta(days=8)

_HEURE = re.compile(r"([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?")
_FORMAT = re.compile(r"[A-Z0-9]{1,10}")

# Les champs qu'un client écrit, et leur valeur quand il ne les donne pas.
DEFAUTS = {
    "nom": None,
    "active": True,
    "heure": None,
    "jours": 0,
    "contexte": "bibliotheque",
    "contexte_id": None,
    "melange": False,
    "genre_id": None,
    "format": None,
    "favoris": False,
    "volume_depart_db": -50.0,
    "volume_cible_db": -35.0,
    "montee_s": 0,
    "fin_mode": "duree",
    "fin_valeur": 60,
}
_MAX_FIN = {"duree": 24 * 60, "pistes": 1000}
# Un INTEGER de Postgres : au-delà, asyncpg lève (500) au lieu d'un refus.
ID_MAX = 2**31 - 1
RESULTAT_MAX = 40  # VARCHAR(40)
_MAX_MONTEE_S = 3600  # la montée du volume dure 1 h au plus (décision de l'opérateur)


# ── les instants ────────────────────────────────────────────────────────


def iso(instant: datetime) -> str:
    """Le format stocké : UTC, à la microseconde, toujours la même longueur."""
    return instant.astimezone(UTC).isoformat(timespec="microseconds")


def lire_iso(valeur: str | None) -> datetime | None:
    return datetime.fromisoformat(valeur) if valeur else None


def local(instant: datetime | None, fuseau: ZoneInfo) -> str | None:
    """Un instant rendu dans le fuseau, avec son décalage (`+01:00`)."""
    return instant.astimezone(fuseau).isoformat(timespec="milliseconds") if instant else None


def decalage(instant: datetime, fuseau: ZoneInfo) -> str:
    minutes = int(instant.astimezone(fuseau).utcoffset().total_seconds() // 60)
    signe = "+" if minutes >= 0 else "-"
    return f"{signe}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def fuseau(nom: str) -> ZoneInfo:
    try:
        return ZoneInfo(nom.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError(f"fuseau inconnu : {nom!r} (attendu : un nom IANA, Europe/Paris)") from None


class FuseauRegle:
    """Le fuseau réglé, relu à chaque usage. Un réglage invalide posé à chaud
    (`Europe/paris`, vide) ne bloque pas le réveil : on garde le dernier
    fuseau valide (sinon `Europe/Paris`), l'écart est journalisé une fois et
    rendu par `avertissement` (horloge, liste des alarmes)."""

    def __init__(self, lire: Callable[[], str], journal: logging.Logger):
        self.lire, self.journal = lire, journal
        self.valide = ZoneInfo("Europe/Paris")
        self.avertissement: str | None = None
        self._signale: str | None = None

    def __call__(self) -> ZoneInfo:
        nom = self.lire()
        try:
            self.valide = fuseau(nom)
        except ValueError as e:
            self.avertissement = f"{e} ; le réveil reste sur {self.valide.key}"
            if nom != self._signale:
                self._signale = nom
                self.journal.warning("réglage fuseau : %s", self.avertissement)
        else:
            self.avertissement = self._signale = None
        return self.valide


def lire_heure(valeur: str) -> time:
    m = _HEURE.fullmatch(valeur)
    if not m:
        raise ValueError(f"heure illisible : {valeur!r}")
    return time(int(m[1]), int(m[2]), int(m[3] or 0))


# ── la prochaine occurrence ─────────────────────────────────────────────


def _instant(jour: date, heure: time, fz: ZoneInfo) -> datetime:
    """L'heure locale de ce jour, en UTC.

    `fold=0` tranche les deux cas des changements d'heure : une heure qui
    n'existe pas (02:30 le jour du passage à l'heure d'été) est lue avec le
    décalage d'avant, et tombe donc une heure plus tard (03:30) ; une heure
    qui existe deux fois (02:30 le jour du retour à l'heure d'hiver) est la
    première des deux."""
    return datetime.combine(jour, heure, tzinfo=fz).astimezone(UTC)


def prochaine_occurrence(fz: ZoneInfo, heure: time, jours: int, apres: datetime) -> datetime | None:
    """La première occurrence strictement après `apres`, en UTC.

    `jours` est un masque (lundi = 1 … dimanche = 64) ; 0 : tous les jours
    conviennent, et c'est à l'appelant de ne garder que la première
    (une alarme unique)."""
    apres = apres.astimezone(UTC)
    depart = apres.astimezone(fz).date()
    for d in range(9):
        jour = depart + timedelta(days=d)
        if jours and not jours & (1 << jour.weekday()):
            continue
        instant = _instant(jour, heure, fz)
        if instant > apres:
            return instant
    return None


def situer(fz: ZoneInfo, heure: time, jours: int, base: datetime, maintenant: datetime) -> tuple[str, datetime | None]:
    """Où en est une alarme active : `("attendre", occurrence à venir)`,
    `("partir", occurrence due)` ou `("manquee", occurrence manquée)`.

    `base` : l'instant après lequel une occurrence compte (la dernière
    traitée, ou le moment où l'alarme a été armée). Une alarme unique n'a
    qu'une occurrence, la première après `base` ; une alarme répétée, si
    plusieurs sont passées, n'est jugée que sur la plus récente."""
    occ = prochaine_occurrence(fz, heure, jours, max(base, maintenant - _HORIZON))
    if occ is None:
        return "attendre", None
    if occ > maintenant:
        return "attendre", occ
    while jours and (suivante := prochaine_occurrence(fz, heure, jours, occ)) is not None and suivante <= maintenant:
        occ = suivante
    return ("partir" if maintenant - occ <= RATTRAPAGE else "manquee"), occ


def base(alarme: dict) -> datetime:
    """Une occurrence compte si elle suit la dernière traitée et le moment
    où l'alarme a été armée (créée, ou modifiée dans son heure, ses jours ou
    son activation) : une alarme créée à 07:05 pour 07:00 ne part pas en
    « rattrapage », et un renommage à 07:00:01 ne fait pas sauter celle de
    07:00."""
    candidats = [lire_iso(alarme["arme_le"]), lire_iso(alarme["derniere_echeance"])]
    return max(c for c in candidats if c is not None)


def occurrence(alarme: dict, fz: ZoneInfo, maintenant: datetime) -> tuple[str, datetime | None]:
    if not alarme["active"]:
        return "inactive", None
    return situer(fz, lire_heure(alarme["heure"]), alarme["jours"], base(alarme), maintenant)


# ── la validation ───────────────────────────────────────────────────────


class Invalide(Exception):
    def __init__(self, erreurs: list[dict]):
        super().__init__("; ".join(f"{e['champ']} : {e['message']}" for e in erreurs))
        self.erreurs = erreurs


def _entier(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def identifiant(v) -> bool:
    return _entier(v) and 0 < v <= ID_MAX


def _nombre(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) and math.isfinite(v)


def valider(donnees: dict, avant: dict | None = None) -> dict:
    """Les valeurs complètes d'une alarme, ou `Invalide` avec chaque motif.

    `avant` : l'alarme modifiée (PUT) ; les champs absents gardent sa valeur.
    Les champs inconnus sont refusés, pour qu'une faute de frappe ne passe
    pas en silence."""
    if not isinstance(donnees, dict):
        raise Invalide([{"champ": "", "message": "un objet JSON est attendu"}])
    erreurs: list[dict] = []

    def refus(champ: str, message: str) -> None:
        erreurs.append({"champ": champ, "message": message})

    for cle in donnees:
        if cle not in DEFAUTS:
            refus(cle, "champ inconnu ou non modifiable")
    v = {k: (avant or DEFAUTS)[k] for k in DEFAUTS}
    v.update({k: donnees[k] for k in donnees if k in DEFAUTS})

    if not isinstance(v["nom"], str) or not v["nom"].strip():
        refus("nom", "obligatoire")
    elif len(v["nom"].strip()) > 80:
        refus("nom", "80 caractères au plus")
    else:
        v["nom"] = v["nom"].strip()

    for champ in ("active", "melange", "favoris"):
        if not isinstance(v[champ], bool):
            refus(champ, "vrai ou faux attendu")

    if not isinstance(v["heure"], str) or not _HEURE.fullmatch(v["heure"]):
        refus("heure", "attendue au format HH:MM ou HH:MM:SS (00:00 à 23:59:59)")
    else:
        h = lire_heure(v["heure"])
        v["heure"] = h.strftime("%H:%M:%S" if h.second else "%H:%M")

    if not _entier(v["jours"]) or not 0 <= v["jours"] <= 127:
        refus("jours", "masque de 0 à 127 attendu (lundi = 1 … dimanche = 64 ; 0 = une seule fois)")

    contexte = v["contexte"]
    if contexte not in CONTEXTES:
        refus("contexte", f"attendu : {', '.join(CONTEXTES)}")
    elif contexte == "bibliotheque":
        if v["contexte_id"] is not None:
            refus("contexte_id", "sans objet pour un tirage dans la bibliothèque")
    elif contexte == "playlist" and _entier(v["contexte_id"]) and v["contexte_id"] <= 0:
        if v["contexte_id"] not in PLAYLISTS_DYNAMIQUES:
            refus("contexte_id", "playlist inconnue : un identifiant de playlist (1 ou plus), "
                  f"ou {PLAYLIST_ALBUMS_FAVORIS} (Albums favoris) ou {PLAYLIST_PISTES_FAVORITES} (Pistes favorites)")
    elif not identifiant(v["contexte_id"]):
        refus("contexte_id", f"identifiant obligatoire pour le contexte « {contexte} »")

    if v["melange"] is True and contexte != "playlist":
        refus("melange", "réservé au contexte playlist")
    if contexte != "bibliotheque":
        for champ in ("genre_id", "format"):
            if v[champ] is not None:
                refus(champ, "filtre réservé au contexte bibliotheque")
        if v["favoris"] is True:
            refus("favoris", "filtre réservé au contexte bibliotheque")
    if v["genre_id"] is not None and not identifiant(v["genre_id"]):
        refus("genre_id", "identifiant de genre attendu")
    if v["format"] is not None:
        fmt = v["format"].strip().upper() if isinstance(v["format"], str) else None
        if not fmt or not _FORMAT.fullmatch(fmt):
            refus("format", "format de fichier attendu (FLAC, MP3…)")
        else:
            v["format"] = fmt

    for champ in ("volume_depart_db", "volume_cible_db"):
        if not _nombre(v[champ]) or not -80 <= v[champ] <= 18:
            refus(champ, "volume de -80 à 18 dB attendu")
        else:
            v[champ] = float(v[champ])

    if not _entier(v["montee_s"]) or not 0 <= v["montee_s"] <= _MAX_MONTEE_S:
        refus("montee_s", f"durée en secondes de 0 à {_MAX_MONTEE_S} (1 h) attendue (0 = volume cible d'emblée)")

    fin = v["fin_mode"]
    if fin not in FINS:
        refus("fin_mode", f"attendu : {', '.join(FINS)}")
    elif fin == "sans_limite":
        if v["fin_valeur"] is not None:
            refus("fin_valeur", "sans objet pour une fin sans limite")
    elif not _entier(v["fin_valeur"]) or not 0 < v["fin_valeur"] <= _MAX_FIN[fin]:
        unite = "minutes" if fin == "duree" else "pistes"
        refus("fin_valeur", f"nombre de {unite} de 1 à {_MAX_FIN[fin]} attendu")

    if erreurs:
        raise Invalide(erreurs)
    return v


async def verifier_references(session, v: dict) -> None:
    """La playlist, l'artiste, l'album ou le genre visés existent (tables du
    cœur, lues sans leurs modèles). Un artiste ou un album à la corbeille ne
    compte pas. Une playlist dynamique (favoris) existe toujours."""
    requetes = {
        "playlist": "SELECT 1 FROM playlists WHERE id = :id",
        "artiste": "SELECT 1 FROM artists WHERE id = :id AND trashed = 0",
        "album": "SELECT 1 FROM albums WHERE id = :id AND trashed = 0",
    }
    erreurs = []
    dynamique = v["contexte"] == "playlist" and v["contexte_id"] in PLAYLISTS_DYNAMIQUES
    if v["contexte"] in requetes and not dynamique:
        if (await session.execute(text(requetes[v["contexte"]]), {"id": v["contexte_id"]})).first() is None:
            erreurs.append({"champ": "contexte_id", "message": f"{v['contexte']} {v['contexte_id']} introuvable"})
    if v["genre_id"] is not None:
        if (await session.execute(text("SELECT 1 FROM libraries WHERE id = :id"), {"id": v["genre_id"]})).first() is None:
            erreurs.append({"champ": "genre_id", "message": f"genre {v['genre_id']} introuvable"})
    if erreurs:
        raise Invalide(erreurs)


# ── la table ────────────────────────────────────────────────────────────

_COLONNES = ", ".join(DEFAUTS)
_PARAMS = ", ".join(f":{c}" for c in DEFAUTS)


async def lister(session, *, actives: bool = False) -> list[dict]:
    where = " WHERE active" if actives else ""
    lignes = await session.execute(text(f"SELECT * FROM {TABLE}{where} ORDER BY heure, id"))
    return [dict(l._mapping) for l in lignes]


async def lire(session, ident: int) -> dict | None:
    ligne = (await session.execute(text(f"SELECT * FROM {TABLE} WHERE id = :id"), {"id": ident})).first()
    return dict(ligne._mapping) if ligne else None


async def premiere(session) -> dict | None:
    ligne = (await session.execute(text(f"SELECT * FROM {TABLE} WHERE NOT test ORDER BY id LIMIT 1"))).first()
    return dict(ligne._mapping) if ligne else None


async def creer(session, v: dict, maintenant: datetime, *, test: bool = False) -> dict:
    instant = iso(maintenant)
    ligne = await session.execute(
        text(
            f"INSERT INTO {TABLE} ({_COLONNES}, test, cree_le, modifie_le, arme_le) "
            f"VALUES ({_PARAMS}, :test, :instant, :instant, :instant) RETURNING *"
        ),
        {**v, "test": test, "instant": instant},
    )
    return dict(ligne.one()._mapping)


_ARMEMENT = ("heure", "jours", "active")


async def modifier(session, ident: int, v: dict, maintenant: datetime, avant: dict) -> dict | None:
    """Ne réarme l'alarme (`arme_le` devient sa base) que si son heure, ses
    jours ou son activation changent."""
    affectations = ", ".join(f"{c} = :{c}" for c in DEFAUTS)
    rearmer = any(v[c] != avant[c] for c in _ARMEMENT)
    arme = ", arme_le = :instant" if rearmer else ""
    ligne = await session.execute(
        text(f"UPDATE {TABLE} SET {affectations}, modifie_le = :instant{arme} WHERE id = :id RETURNING *"),
        {**v, "id": ident, "instant": iso(maintenant)},
    )
    trouvee = ligne.first()
    return dict(trouvee._mapping) if trouvee else None


async def supprimer(session, ident: int) -> bool:
    return (await session.execute(text(f"DELETE FROM {TABLE} WHERE id = :id RETURNING id"), {"id": ident})).first() is not None


async def prendre(
    session, ident: int, occ: datetime, *, lu: str, execution: datetime | None, resultat: str
) -> dict | None:
    """Note qu'une occurrence est traitée (partie si `execution`, sinon
    manquée), **si personne ne l'a fait avant** : c'est cette écriture
    conditionnelle qui empêche un double départ, même entre deux
    ordonnanceurs. Une alarme unique se désactive dans la même écriture.

    `lu` : l'`arme_le` de l'alarme lue au moment de calculer `occ`. Si elle a
    été réarmée depuis (07:00 passée à 08:00 entre la lecture et ici),
    l'occurrence ne vaut plus et rien n'est pris.
    Rend l'alarme à jour, ou None si l'occurrence était déjà prise."""
    ligne = await session.execute(
        text(
            f"UPDATE {TABLE} SET derniere_echeance = :occ, "
            "derniere_execution = COALESCE(:execution, derniere_execution), "
            "dernier_resultat = :resultat, "
            "active = CASE WHEN jours = 0 THEN FALSE ELSE active END "
            "WHERE id = :id AND active AND arme_le <= :lu "
            "AND (derniere_echeance IS NULL OR derniere_echeance < :occ) "
            "RETURNING *"
        ),
        {
            "id": ident, "occ": iso(occ), "lu": lu,
            "execution": iso(execution) if execution else None, "resultat": resultat[:RESULTAT_MAX],
        },
    )
    trouvee = ligne.first()
    return dict(trouvee._mapping) if trouvee else None


async def noter_resultat(session, ident: int, resultat: str) -> None:
    await session.execute(text(f"UPDATE {TABLE} SET dernier_resultat = :r WHERE id = :id"), {"id": ident, "r": resultat[:RESULTAT_MAX]})


async def supprimer_tests_finis(session) -> int:
    """Les alarmes de test passées (prises, donc inactives) qu'un arrêt
    d'unisson a laissées avant leur suppression."""
    lignes = await session.execute(text(f"DELETE FROM {TABLE} WHERE test AND NOT active RETURNING id"))
    return len(lignes.all())


def retard_ms(alarme: dict) -> int | None:
    echeance, execution = lire_iso(alarme.get("derniere_echeance")), lire_iso(alarme.get("derniere_execution"))
    # Une échéance manquée garde l'exécution d'avant : pas de retard à montrer.
    if echeance is None or execution is None or execution < echeance:
        return None
    return round((execution - echeance).total_seconds() * 1000)


def vue(alarme: dict, fz: ZoneInfo, maintenant: datetime) -> dict:
    """L'alarme rendue par l'API : ses champs, sa prochaine occurrence (dans
    le fuseau, avec son décalage ; null si inactive) et le retard de son
    dernier départ."""
    etat, occ = occurrence(alarme, fz, maintenant)
    return {
        "id": alarme["id"],
        **{k: alarme[k] for k in DEFAUTS},
        "test": alarme["test"],
        "prochaine": local(occ, fz),
        "derniere_echeance": local(lire_iso(alarme["derniere_echeance"]), fz),
        "derniere_execution": local(lire_iso(alarme["derniere_execution"]), fz),
        "dernier_retard_ms": retard_ms(alarme),
        "dernier_resultat": alarme["dernier_resultat"],
        "cree_le": alarme["cree_le"],
        "modifie_le": alarme["modifie_le"],
        "arme_le": alarme["arme_le"],
    }

