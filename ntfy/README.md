# ntfy — le fil du matin sur le téléphone

Le matin, unisson sait ce qui s'est passé la nuit : albums rangés, arrivées à
trier, versions meilleures qui attendent un choix, téléchargements en échec,
disque presque plein. Ce plugin pousse ce **fil du matin** sur le téléphone
par [ntfy](https://ntfy.sh) : un **résumé** une fois par jour, à l'heure
choisie, et les **alertes immédiates** dès qu'un événement assez grave
arrive. Un clic sur la notification ouvre le fil dans l'admin.

Demande le cœur **≥ 0.11** (`ctx.canal_notification`, unisson#1258). Le
plugin n'a ni table ni écran : ses réglages se posent depuis la page
**Plugins** (bouton « Réglages »).

## Ce qu'il fait

- **Résumé quotidien**, à `heure_resume` (heure locale du serveur
  d'unisson) : les comptes depuis le résumé précédent (« 2 à décider · 38
  rangés · 1 échec »), puis ce qui attend une décision et ce qui a échoué.
  Rien de neuf : rien n'est envoyé. Un redémarrage après l'heure ne le
  renvoie pas.
- **Alertes immédiates** : chaque événement d'une gravité au moins égale à
  `gravite_alerte` part dans la minute (au commit de l'événement). Au-delà
  de cinq en attente, un seul message « N alertes ». Priorité ntfy : 4 pour
  `avertissement` (un téléchargement en échec), 5 pour `critique` (l'espace
  disque sous le minimum).
- **Lien profond** : la notification ouvre le fil (`click`, et un bouton
  « Ouvrir le fil »). Par défaut `<adresse réseau d'unisson>/admin/fil`
  (Paramètres → Réseau) ; `lien_fil` la remplace, par exemple pour une
  adresse publique derrière un proxy.
- **Serveur injoignable** : rien d'autre n'attend. L'échec est journalisé
  (journal `backend.services.fil` du cœur, avec le code HTTP, jamais le jeton) ; une alerte
  est retentée cinq minutes plus tard tant qu'elle a moins de six heures, le
  résumé jusqu'à la fin du jour. Le fil, lui, reste dans l'admin.

## Réglages

| Clé | Défaut | Rôle |
|---|---|---|
| `serveur` | `https://ntfy.sh` | le serveur ntfy, `http(s)://hôte[:port]` |
| `sujet` | — (requis) | le sujet (topic) auquel le téléphone est abonné ; lettres, chiffres, `-` et `_` |
| `jeton` | — | jeton d'accès ntfy (`tk_…`), **secret** : jamais rendu par l'API ; vide = sujet public |
| `heure_resume` | `07:30` | `HH:MM` ; vide = pas de résumé |
| `gravite_alerte` | `avertissement` | `info`, `avertissement` ou `critique` ; vide = pas d'alerte immédiate |
| `lien_fil` | — | l'adresse ouverte au clic ; vide = `<adresse réseau>/admin/fil` |

Sans sujet, ou avec un serveur, une heure ou une gravité illisible,
l'activation est refusée et la page Plugins dit pourquoi. Tous les réglages
sont relus à chaque envoi : les changer vaut sans réactiver.

Un sujet public sur `ntfy.sh` est lisible par quiconque en devine le nom :
prendre un nom long et imprévisible, ou un serveur à soi avec un jeton.

## Retour arrière

Désactiver le plugin retire le canal : plus rien ne part, le fil reste dans
l'admin. Rien n'est écrit ailleurs qu'en base (`fil_canaux`, la mémoire du
dernier envoi, tenue par le cœur).

## Tests

Ils tournent dans le harnais du cœur (≥ 0.11), contre un vrai serveur HTTP
local qui joue ntfy, et par le vrai chargeur :

```sh
cd <checkout du cœur>
flock /tmp/unisson-test-db.lock env PYTHONPATH=. \
  TEST_DATABASE_URL=postgresql+asyncpg://dedup:dedup@localhost:5432/dedup_test \
  .venv/bin/python -m pytest <dépôt>/ntfy/tests \
  -c backend/pyproject.toml --rootdir=backend -p backend.tests.conftest -q
```
