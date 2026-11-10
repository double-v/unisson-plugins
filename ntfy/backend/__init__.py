"""ntfy : le fil du matin d'unisson poussé sur le téléphone (unisson-plugins#19).

Le cœur (0.11) tient le fil, rédige le résumé et décide quand une alerte
part ; ce plugin n'est qu'un **canal** : il pose chaque message chez ntfy,
dans le sujet auquel le téléphone est abonné. Un clic sur la notification
ouvre le fil de l'admin.

On publie en JSON (`POST <serveur>/`, `{"topic": …}`) plutôt qu'en en-têtes
`Title:` : un titre accentué (« 2 à décider · 38 rangés ») n'a pas sa place
dans un en-tête HTTP, et ntfy le rendrait illisible.

Le serveur injoignable n'est l'affaire que de ce canal : `envoyer` lève, le
cœur journalise et retente plus tard, rien d'autre n'attend (borne de 10 s
du cœur, et la nôtre, plus courte).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx

from unisson.plugin import GRAVITES, CanalNotification, Contexte, MessageNotification

DELAI_S = 5.0

# ntfy : 1 min, 2 low, 3 default, 4 high, 5 urgent.
PRIORITES = {"info": 3, "avertissement": 4, "critique": 5}
ETIQUETTES = {"info": ["information_source"], "avertissement": ["warning"], "critique": ["rotating_light"]}

_SUJET = re.compile(r"^[-_A-Za-z0-9]{1,64}$")
_HEURE = re.compile(r"^(\d{1,2}):(\d{2})$")


# ntfy refuse (ou change en pièce jointe) un message au-delà de 4 096 octets :
# on coupe avant, sur une frontière de caractère, et on le dit.
MAX_OCTETS = 3500
SUITE = "\n… (suite dans le fil)"


class NtfyInjoignable(RuntimeError):
    """Le serveur n'a pas pris le message : le motif, jamais le jeton ni le
    mot de passe d'une adresse `https://user:pass@hôte`."""


def masquer(url: str) -> str:
    """L'adresse sans son `user:pass@` : elle part au journal."""
    parties = urlsplit(url)
    if "@" not in parties.netloc:
        return url
    hote = parties.netloc.rsplit("@", 1)[1]
    return parties._replace(netloc=f"***@{hote}").geturl()


def tronquer(texte: str, max_octets: int = MAX_OCTETS) -> str:
    brut = texte.encode("utf-8")
    if len(brut) <= max_octets:
        return texte
    garde = max_octets - len(SUITE.encode("utf-8"))
    return brut[:garde].decode("utf-8", errors="ignore") + SUITE


def valider_serveur(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    parties = urlsplit(url)
    if parties.scheme not in ("http", "https") or not parties.netloc:
        raise ValueError(f"serveur ntfy « {masquer(url)} » : une adresse http(s)://hôte est attendue")
    return url


def valider_sujet(sujet: str) -> str:
    sujet = (sujet or "").strip()
    if not _SUJET.match(sujet):
        raise ValueError("sujet ntfy à régler : lettres, chiffres, - et _, 64 au plus")
    return sujet


def valider_heure(heure: str) -> str:
    heure = (heure or "").strip()
    m = _HEURE.match(heure)
    if heure and (not m or int(m.group(1)) > 23 or int(m.group(2)) > 59):
        raise ValueError(f"heure du résumé « {heure} » : HH:MM attendu, ou vide")
    return heure


def valider_gravite(gravite: str) -> str:
    gravite = (gravite or "").strip()
    if gravite and gravite not in GRAVITES:
        raise ValueError(f"gravité « {gravite} » : {', '.join(GRAVITES)}, ou vide")
    return gravite


def corps(message: MessageNotification, sujet: str, lien_fil: str | None) -> dict:
    """Le JSON que ntfy attend, depuis le message rédigé par le cœur."""
    resume = message.genre == "resume"
    donnees = {
        "topic": sujet,
        "title": f"unisson · {message.titre}" if resume else message.titre,
        "message": tronquer(message.texte or message.titre),
        "priority": 3 if resume else PRIORITES.get(message.gravite, 3),
        "tags": ["sunrise"] if resume else ETIQUETTES.get(message.gravite, []),
    }
    lien = lien_fil or message.lien
    if lien:
        donnees["click"] = lien
        donnees["actions"] = [{"action": "view", "label": "Ouvrir le fil", "url": lien}]
    return donnees


async def publier(serveur: str, jeton: str, donnees: dict) -> None:
    entetes = {"Authorization": f"Bearer {jeton}"} if jeton else {}
    try:
        async with httpx.AsyncClient(timeout=DELAI_S) as client:
            r = await client.post(f"{serveur}/", json=donnees, headers=entetes)
    except httpx.HTTPError as e:
        # `str(e)` d'httpx peut citer l'URL complète : on ne garde que le type.
        raise NtfyInjoignable(f"{masquer(serveur)} injoignable ({type(e).__name__})") from None
    if r.status_code >= 400:
        raise NtfyInjoignable(f"{masquer(serveur)} a refusé le message : HTTP {r.status_code} {r.text[:200]}")


def enregistrer(ctx: Contexte) -> None:
    # Refuser tout de suite une configuration inutilisable : le plugin passe
    # « erreur » avec ce motif, plutôt qu'un canal qui échouerait chaque nuit.
    valider_serveur(ctx.reglage("serveur"))
    valider_sujet(ctx.reglage("sujet"))
    valider_heure(ctx.reglage("heure_resume"))
    valider_gravite(ctx.reglage("gravite_alerte"))

    async def envoyer(message: MessageNotification) -> None:
        # Relus à chaque envoi : un réglage changé vaut sans réactiver.
        serveur = valider_serveur(ctx.reglage("serveur"))
        sujet = valider_sujet(ctx.reglage("sujet"))
        lien_fil = (ctx.reglage("lien_fil") or "").strip() or None
        await publier(serveur, ctx.secret("jeton"), corps(message, sujet, lien_fil))
        ctx.journal.info("ntfy : %s envoyé (%s)", message.genre, message.titre)

    ctx.canal_notification(CanalNotification(
        nom="push",
        envoyer=envoyer,
        heure_resume=lambda: ctx.reglage("heure_resume"),
        gravite_alerte=lambda: ctx.reglage("gravite_alerte"),
    ))
