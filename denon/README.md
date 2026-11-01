# Denon

Partage un ampli Denon entre unisson, Hublot et les autres clients. Il garde
une seule connexion telnet et expose **la même API HTTP que `denon-api`**,
qu'il remplace : plus de conteneur à part. Plugin **officiel** d'unisson,
**inactif par défaut** (tout le monde n'a pas un Denon). C'est le premier lot
du #343 (spec 023 du cœur). Le réveil (alarmes, lecture UPnP d'une playlist)
viendra sur ce lien.

## Ce qu'il apporte

- **Le lien telnet unique.** Un AVR n'accepte qu'une connexion, et perd les
  commandes trop rapprochées. Le lien met les commandes en file, les envoie à
  la cadence réglée et se reconnecte (attente de 1 s, qui double jusqu'à
  30 s). Il tient aussi l'état poussé par l'ampli : alimentation, volume,
  sourdine, source. C'est une réécriture en Python de `denon-api`
  (`server/denon-link.js`), au comportement près. L'hôte et le port sont
  relus à chaque connexion.
- **Les pilotes** (`backend/pilotes.py`) : tout ce qui est propre à un
  modèle. Premier pilote : `avrx4000`.
- **L'API de `denon-api`, à l'identique** (chemins, corps, réponses, codes
  d'erreur), sous `/api/plugins/denon/` :

  | Méthode | Route | Corps | Réponse |
  |---|---|---|---|
  | GET | `/healthz` (sans jeton) | | `{ok, denon}` |
  | GET | `/api/state` | | `{connected, power, volume, mute, source, updatedAt, host, port}` |
  | GET | `/api/queue` | | `{pending, cadenceMs}` |
  | POST | `/api/command` | `{command}` | 400 `command_required`, 503 si invalide |
  | POST | `/api/power` | `{on}` | `{accepted, command}` |
  | POST | `/api/mute` | `{muted}` | idem |
  | POST | `/api/source` | `{source}` | 400 `invalid_source` |
  | POST | `/api/volume` | `{db}` (-80 à 18) | 400 `invalid_volume` |
  | POST | `/api/volume/up`, `/api/volume/down` | | idem |

  Ampli injoignable : 503 `denon_unreachable`. Si un `jeton` est réglé, toute
  route sauf `/healthz` exige `Authorization: Bearer <jeton>`, sinon 401
  `{"error": "unauthorized"}`.
- **L'écoute à part** (`port_ecoute`, désactivée à 0) : la même API servie
  seule sur un port, à l'adresse exacte de l'ancien conteneur
  (`http://<nas>:8100/api/state`). Hublot bascule ainsi sans changer une
  ligne. Si le port est pris, l'écoute le journalise et le plugin continue
  sous `/api/plugins/denon/`. Elle ne touche pas aux signaux d'unisson.
- **Le client UPnP/DLNA** (`backend/dlna.py`, pas encore branché : lot 4 du
  réveil) : lit la description du lecteur, ses formats (`GetProtocolInfo`),
  pilote AVTransport et compose le DIDL-Lite d'une piste. Rien de propre à
  Denon ; testé contre un faux lecteur HTTP nourri de réponses de l'AVR-X4000.

## Réglages

| Clé | Défaut | Rôle |
|---|---|---|
| `hote` | vide | IP de l'ampli ; vide : le lien attend |
| `port_telnet` | 23 | |
| `cadence_ms` | 900 | délai entre deux commandes |
| `pilote` | `avrx4000` | un pilote inconnu refuse l'activation, avec son motif |
| `jeton` (secret) | vide | vide : routes ouvertes, comme `denon-api` |
| `port_ecoute` | 0 | lu à l'activation : le changer demande de réactiver |

`denon_host` et `denon_telnet_port`, que le cœur recopie depuis
`DEDUP_DENON_*` (spec 023, US3), sont repris dans `hote` et `port_telnet`.

## Basculer depuis `denon-api`

L'ampli n'accepte qu'une connexion telnet : le plugin et le conteneur ne
peuvent pas tourner ensemble.

1. Installer le plugin. Régler `jeton` (le `DENON_API_TOKEN` actuel),
   `cadence_ms` et `port_ecoute = 8100`, mais laisser `hote` vide.
2. Arrêter le conteneur `denon-api` sur le TrueNAS : il libère le telnet et
   le port 8100 de l'hôte.
3. Publier le port dans le compose d'unisson (`- "8100:8100"` à côté de
   `8090:8000`), puis redéployer. Pas avant l'étape 2 : le conteneur
   d'unisson ne démarrerait pas, faute de pouvoir prendre le port.
4. Régler `hote = 192.168.1.184` et activer le plugin.
5. Vérifier : `curl -H "Authorization: Bearer …" http://192.168.1.136:8100/api/state`
   rend `connected: true`, et la tuile Denon de Hublot répond.

Retour arrière : désactiver le plugin, retirer le port du compose, relancer
`denon-api`. Le dépôt `denon-api` reste.

## Tests

Ils tournent dans le harnais du cœur, depuis le checkout d'unisson :

```sh
PYTHONPATH=. TEST_DATABASE_URL=postgresql+asyncpg://dedup:dedup@localhost:5432/dedup_test \
  .venv/bin/python -m pytest <unisson-plugins>/denon/tests \
  -c backend/pyproject.toml --rootdir=backend -p backend.tests.conftest
```

Les faux sont posés à la frontière : un faux ampli TCP, un vrai serveur HTTP.
La non-régression de Hublot rejoue ses appels, puis exécute son vrai client
(`plugins/denon/plugin.js`) avec node contre l'écoute à part. Elle se saute
si node ou le dépôt Hublot manquent (`HUBLOT_SRC`, défaut `../hublot`).
