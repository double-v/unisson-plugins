# Denon

Partage un ampli Denon entre unisson, Hublot et les autres clients. Il garde
une seule connexion telnet et expose **la même API HTTP que `denon-api`**,
qu'il remplace : plus de conteneur à part. Plugin **officiel** d'unisson,
**inactif par défaut** (tout le monde n'a pas un Denon). C'est le premier lot
du #343 (spec 023 du cœur). Le réveil s'y ajoute (conception :
[`docs/reveil.md`](docs/reveil.md)) : depuis la 0.2.0, les alarmes et leur
ordonnanceur ; la lecture UPnP (la séance) viendra au lot 4.

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
- **Les alarmes du réveil** (0.2.0, `backend/alarmes.py`), dans la table
  `plugin_denon.alarmes` (migration du plugin). Une heure locale (`HH:MM` ou
  `HH:MM:SS`, dans le réglage `fuseau`), un masque de jours (lundi = 1 …
  dimanche = 64 ; 0 = une seule fois), ce qui se joue (`playlist`,
  `bibliotheque` avec ses filtres genre, format, favoris, `artiste`,
  `album`), les volumes de départ et cible (-80 à 18 dB) et la montée (1 h au plus), la
  fin (`duree` en minutes, `pistes`, `sans_limite`). Changement d'heure :
  une heure qui n'existe pas (02:30 au passage à l'heure d'été) part une
  heure plus tard ; une heure qui existe deux fois part à la première.
- **L'ordonnanceur** (`backend/ordonnanceur.py`), tâche de fond : il dort
  jusqu'à la prochaine échéance (30 s au plus), et toute écriture d'alarme le
  réveille ; précision d'environ une seconde. Il note l'échéance traitée
  avant de déclencher : aucune alarme ne part deux fois, même après un
  redémarrage. **Rattrapage** : jusqu'à 10 min de retard (unisson
  redémarrait), l'alarme part ; au-delà, elle est `manquee`. Une alarme
  créée ou modifiée après son heure attend la prochaine, sans rattrapage.
  Une alarme unique se désactive après son passage. Seul un changement
  d'heure, de jours ou d'activation réarme une alarme : un renommage à 07:00:01
  ne fait pas sauter celle de 07:00. Un passage en échec (base
  indisponible) est réessayé une seconde plus tard ; au démarrage, les
  alarmes de test passées qu'un arrêt a laissées sont supprimées. Dans ce lot, le
  déclenchement est journalisé (`dernier_resultat = "declenchee"`) ; la
  séance viendra au lot 4.
- **Les routes du réveil**, sous `/api/plugins/denon/reveil/`, avec le même
  jeton (pas sur l'écoute à part) :

  | Méthode | Route | Corps | Réponse |
  |---|---|---|---|
  | GET | `/alarmes` | | `{fuseau, alarmes: [...]}`, chacune avec `prochaine` (ISO dans le fuseau, null si inactive), `dernier_resultat`, `dernier_retard_ms` |
  | POST | `/alarmes` | l'alarme | 201 ; 422 `{error: "alarme_invalide", erreurs: [{champ, message}]}` |
  | PUT | `/alarmes/{id}` | les champs à changer | l'alarme revalidée en entier, réarmée ; 404 `alarme_introuvable` |
  | DELETE | `/alarmes/{id}` | | 204 ; 404 |
  | POST | `/tester` | `{dans_s: 5 \| 10, alarme_id?}` | 201 `{alarme, horloge, echeance, echeance_utc}` |
  | GET | `/tester/{id}` | | `{etat: en_attente \| partie \| manquee, echeance, depart, retard_ms, dernier_resultat}` |
  | GET | `/horloge` | | `{fuseau, local, decalage, utc, avertissement}` |

  Un identifiant (chemin, `contexte_id`, `genre_id`, `alarme_id`) au-delà
  de 2³¹−1 est refusé en 422.

  Le **testeur de fuseau** crée une alarme unique à maintenant + 5 ou 10 s
  (arrondi à la seconde suivante, nom « Test 07:42:15 »), passée par le vrai
  ordonnanceur. Elle reprend le contexte et les volumes de l'alarme choisie
  (par défaut la première ; sans alarme : un tirage de la bibliothèque à
  -50 dB), et finit toujours après une piste. Pendant l'heure en double du
  retour à l'heure d'hiver, une échéance que l'heure locale ne désigne pas
  est refusée (422). Elle se supprime après son
  passage ; son résultat reste lisible par `GET /tester/{id}` (en mémoire,
  les 20 derniers, perdus au redémarrage).

## Réglages

| Clé | Défaut | Rôle |
|---|---|---|
| `hote` | vide | IP de l'ampli ; vide : le lien attend |
| `port_telnet` | 23 | |
| `cadence_ms` | 900 | délai entre deux commandes |
| `pilote` | `avrx4000` | un pilote inconnu refuse l'activation, avec son motif |
| `jeton` (secret) | vide | vide : routes ouvertes, comme `denon-api` |
| `port_ecoute` | 0 | lu à l'activation : le changer demande de réactiver |
| `fuseau` | `Europe/Paris` | nom IANA : l'heure des alarmes est une heure locale ; un fuseau inconnu refuse l'activation. Réglé invalide à chaud, le réveil garde le dernier bon fuseau, le journalise une fois et le dit dans `avertissement` (`/horloge`, `/alarmes`) |

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

Les faux sont posés à la frontière : un faux ampli TCP, un vrai serveur HTTP,
une horloge injectée dans l'ordonnanceur. La migration est jouée dans
`plugin_denon` sur la base de test, et le schéma retiré après chaque test.
Le testeur de fuseau est éprouvé en temps réel : `dans_s = 5` doit partir
entre 5 et 6,5 s.
La non-régression de Hublot rejoue ses appels, puis exécute son vrai client
(`plugins/denon/plugin.js`) avec node contre l'écoute à part. Elle se saute
si node ou le dépôt Hublot manquent (`HUBLOT_SRC`, défaut `../hublot`).
