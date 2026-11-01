# Denon

Partage un ampli Denon entre unisson, Hublot et les autres clients. Il garde
une seule connexion telnet et expose **la même API HTTP que `denon-api`**,
qu'il remplace : plus de conteneur à part. Plugin **officiel** d'unisson,
**inactif par défaut** (tout le monde n'a pas un Denon). C'est le premier lot
du #343 (spec 023 du cœur). Le réveil s'y ajoute (conception :
[`docs/reveil.md`](docs/reveil.md)) : depuis la 0.2.0, les alarmes et leur
ordonnanceur ; depuis la 0.3.0, la séance qui allume l'ampli et lui fait
jouer la musique d'unisson par UPnP. Depuis la 0.4.0, ses écrans : la page
« Réveil » de l'admin, dans Extensions. Il demande le cœur **0.6** (flux
pour lecteurs réseau, spec 023 ; garde « même origine » des routes du
réveil, unisson#1070).

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
- **Le client UPnP/DLNA** (`backend/dlna.py`) : lit la description du
  lecteur, ses formats (`GetProtocolInfo`), pilote AVTransport et compose le
  DIDL-Lite d'une piste. Rien de propre à Denon ; testé contre un faux
  lecteur HTTP nourri de réponses de l'AVR-X4000.
- **Les alarmes du réveil** (0.2.0, `backend/alarmes.py`), dans la table
  `plugin_denon.alarmes` (migration du plugin). Une heure locale (`HH:MM` ou
  `HH:MM:SS`, dans le réglage `fuseau`), un masque de jours (lundi = 1 …
  dimanche = 64 ; 0 = une seule fois), ce qui se joue (`playlist`, y compris
  depuis la 0.4.1 les playlists dynamiques -1 « Albums favoris » et -2
  « Pistes favorites », cœur 0.7 ou plus, `bibliotheque` avec ses filtres genre, format, favoris, `artiste`,
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
  alarmes de test passées qu'un arrêt a laissées sont supprimées. Une alarme
  qui part lance la séance.
- **La séance** (0.3.0, `backend/seance.py`), une seule à la fois : une
  alarme qui part pendant une séance la remplace (sauf si elle-même ne peut
  pas partir).
  1. *Préparer*, sans toucher à l'ampli : l'adresse réseau d'unisson, le lien
     telnet (5 s pour se reconnecter), les formats du lecteur (une fois par
     séance), les pistes (`pistes_playlist`, mélangée si demandé, ou
     `tirer_pistes`) et le flux de la première. Si l'une manque, l'ampli
     n'est pas réveillé et le résultat le dit.
  2. *Allumer* : `ZMON` (la zone principale seule depuis la 0.4.2 ; `PWON`
     réveillait aussi les zones 2 et 3), le volume de départ (la cible si `montee_s = 0`), et
     la source réseau du pilote s'il en a une (aucune sur l'AVR-X4000 depuis
     la 0.4.1 : `SINET` y coupe la lecture DLNA, R0 du 2026-11-01). On prend
     la main quelle que soit la source.
  3. *Attendre* `delai_reveil_s`, renvoyer volume (et source), puis `Play`
     jusqu'à `PLAYING` (3 essais). Un `STOPPED` juste après le début d'une
     piste, notre URI en place, est une lecture refusée : piste suivante,
     `lecture_impossible` après 3 refus de suite.
  4. *Jouer* : `SetAVTransportURI` → `Play` → `marquer_jouee`, la suivante
     en attente par `SetNextAVTransportURI`. **Repli** si l'ampli refuse
     `SetNext` ou s'arrête en fin de piste sans enchaîner :
     `SetAVTransportURI` + `Play` de la suivante.
  5. *Suivre* toutes les 2 s (`GetTransportInfo`, `GetPositionInfo`) : quand
     `TrackURI` passe à la suivante, `marquer_jouee` et la suivante d'après
     en attente. Une piste au flux impossible (fichier absent, aucun format
     commun) est sautée et journalisée.
  6. *Monter le volume* par pas de 0,5 dB sur `montee_s`. Elle s'arrête si
     l'ampli pousse un volume qui n'est pas l'un de nos pas, ou qui
     redescend sous le plus haut écho déjà vu : quelqu'un y a touché.
  7. *Finir* : `duree` → `Stop` puis `ZMOFF` à l'échéance ; `pistes` →
     `fin_valeur` pistes puis `ZMOFF` ; `sans_limite` → des lots de 50
     rechargés, jamais de veille (`duree` recharge aussi). **Reprise de la
     main** (autre source, `Stop` ou `Pause` venus d'ailleurs, autre média,
     mise en veille) : la séance s'arrête, sans mise en veille. Un
     `STOPPED` est une fin de piste si la piste a joué sa durée, à 4 s près
     (1,5 × le suivi + 1 s) ; sinon c'est un `Stop` venu d'ailleurs. Sans
     durée connue, un `STOPPED` alors que `RelTime` avançait est un `Stop`
     d'ailleurs. Juste après un changement de piste, un `STOPPED` est ignoré
     4 s ; au repli, une piste qui ne démarre pas est sautée.
  8. *Fin anormale* après `ZMON` (`lecture_impossible`, erreur) : `Stop`
     puis `ZMOFF`. En `duree`, UPnP perdu n'arrête pas la séance : la
     veille part par telnet à l'échéance ; en `pistes`, la veille part tout
     de suite ; en `sans_limite`, pas de veille. **Désactiver le plugin**, ou
     **redémarrer unisson**, en pleine séance : `Stop`, puis `ZMOFF` si
     le lien répond encore, avant de fermer. Le cœur (correctif #1068,
     présent dans le 0.6 que le plugin demande) laisse 10 s en tout aux
     tâches des plugins à l'arrêt ; la séance tient sous 8 s au pire
     (`Stop` 1,5 s, veille 2 s, budget de 6 s avec les écritures en vol,
     puis 0,5 s pour le lien et 0,5 s pour le client HTTP).

  Le résultat va dans `dernier_resultat` : `en_cours`, puis `joue`,
  `reprise_en_main`, `arretee`, `remplacee`, `pistes_epuisees`,
  `lecture_impossible`, `plugin_desactive`, ou dès la préparation
  `adresse_reseau_non_reglee`, `ampli_injoignable`, `aucune_piste`,
  `aucun_format_commun`, `fichier_absent`, `contexte_inconnu`. Chaque étape
  est journalisée (`unisson.plugin.denon`).
- **Les routes du réveil**, sous `/api/plugins/denon/reveil/` (pas sur
  l'écoute à part), protégées par la garde « même origine » du cœur
  (`meme_origine`, cœur 0.6), et **non par le jeton** : l'admin, qui sert la
  page « Réveil », n'envoie pas d'`Authorization`. Une écriture venue d'une
  page d'un autre site, ou d'un hôte qu'unisson ne sert pas
  (`DEDUP_ALLOWED_HOSTS`), reçoit 403. Le jeton reste celui de l'API de
  denon-api :

  | Méthode | Route | Corps | Réponse |
  |---|---|---|---|
  | GET | `/alarmes` | | `{fuseau, alarmes: [...]}`, chacune avec `prochaine` (ISO dans le fuseau, null si inactive), `dernier_resultat`, `dernier_retard_ms` |
  | POST | `/alarmes` | l'alarme | 201 ; 422 `{error: "alarme_invalide", erreurs: [{champ, message}]}` |
  | PUT | `/alarmes/{id}` | les champs à changer | l'alarme revalidée en entier, réarmée ; 404 `alarme_introuvable` |
  | DELETE | `/alarmes/{id}` | | 204 ; 404 |
  | POST | `/tester` | `{dans_s: 5 \| 10, alarme_id?}` | 201 `{alarme, horloge, echeance, echeance_utc}` |
  | GET | `/tester/{id}` | | `{etat: en_attente \| partie \| manquee, echeance, depart, retard_ms, dernier_resultat}` |
  | GET | `/horloge` | | `{fuseau, local, decalage, utc, avertissement}` |
  | POST | `/alarmes/{id}/essayer` | | 202 `{resultat: "en_cours", seance, derniere}` ; 409 `{error, message, reglage?}` si elle ne peut pas partir ; 404 |
  | GET | `/seance` | | `{seance, derniere}` : alarme, `etat` (`preparation`, `reveil`, `lecture`, `finie`), `piste` et `suivante` (titre, artiste, album, pochette), `volume`, `volume_cible`, `montee`, `fin_mode`, `fin_prevue`, `pistes_restantes`, `pistes_jouees`, `sautees`, `enchainement` (`suivante` ou `repli`), `resultat` |
  | POST | `/seance/arreter` | | `{arretee, seance, derniere}` : `Stop`, sans mise en veille |
  | GET | `/diagnostic` | | `{ok, problemes, telnet, upnp: {joignable, description, formats, erreur}, adresse_reseau: {reglee, adresse, reglage: "/admin/settings#reseau", message}, pilote: {source_reseau, delai_reveil_s, plafond}, conseils, horloge, seance}` |

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
- **La page « Réveil »** de l'admin (Extensions, `/admin/p/denon/reveil`),
  d'après le prototype validé ([`docs/proto-reveil.html`](docs/proto-reveil.html)) :
  - l'onglet **Alarmes** : interrupteur, heure et jours, ce qui se joue,
    prochaine occurrence et dernier résultat, « Essayer maintenant » (le
    refus 409 se dit sur la ligne), modifier, supprimer (avec confirmation) ;
    les états vide, chargement et erreur ;
  - le **formulaire** sur sa propre page (`?alarme=nouvelle` ou
    `?alarme=<id>`, « ‹ Réveil » pour revenir) : jours, ce qui se joue
    (playlists du player, genres, recherche d'artistes et d'albums par les
    API du cœur), volumes avec l'alerte au-delà de −15 dB, montée au
    curseur (2, 5, 10, 15 min, jusqu'à 1 h) avec sa courbe, et la fin ; les
    refus 422 s'affichent champ par champ ;
  - le **bandeau de séance** (allumage, piste, volume qui monte, fin prévue)
    avec « Arrêter », puis l'annonce de l'arrêt ou de l'échec ;
  - l'onglet **Diagnostic** : telnet, UPnP, adresse d'unisson, formats, le
    fuseau (réglage du plugin), les trois horloges et l'écart « comparé à
    l'heure de ce navigateur », le testeur 5 s / 10 s (son résultat reste
    60 s dans la liste, et dans la carte « L'heure » jusqu'au test suivant),
    les conseils ; une pastille sur l'onglet quand quelque chose ne va pas.

  Un `jeton` réglé (pour Hublot) ne gêne pas la page : les routes du
  réveil suivent la garde « même origine ». Ouverte sous un nom d'hôte
  qu'unisson ne sert pas, la page reçoit 403 et le dit.

  Les sources sont dans `front/admin-src/` (SFC, primitives `@ds`, sans
  `<style>`), compilées dans `front/admin/index.js`, qui est versionné :

  ```sh
  ln -s <checkout unisson>/frontend/node_modules node_modules   # ou npm install
  npm run build
  ```

## Réglages

| Clé | Défaut | Rôle |
|---|---|---|
| `hote` | vide | IP de l'ampli ; vide : le lien attend |
| `port_telnet` | 23 | |
| `cadence_ms` | 900 | délai entre deux commandes |
| `pilote` | `avrx4000` | un pilote inconnu refuse l'activation, avec son motif |
| `jeton` (secret) | vide | l'API de denon-api (`/api/*`, ici et sur l'écoute à part) ; vide : routes ouvertes, comme `denon-api`. Les routes du réveil ne le demandent pas (garde « même origine ») |
| `port_ecoute` | 0 | lu à l'activation : le changer demande de réactiver |
| `hote_upnp` | vide | l'hôte UPnP de l'ampli (description `http://<hôte>:8080/description.xml`), ou l'URL complète de sa description ; vide : `hote`. Relu à chaud |
| `delai_reveil_s` | vide | secondes entre `ZMON` et le premier `Play` ; vide : celui du pilote (8 s sur l'AVR-X4000). Relu à chaque séance |
| `fuseau` | `Europe/Paris` | nom IANA : l'heure des alarmes est une heure locale ; un fuseau inconnu refuse l'activation. Réglé invalide à chaud, le réveil garde le dernier bon fuseau, le journalise une fois et le dit dans `avertissement` (`/horloge`, `/alarmes`) |

`denon_host` et `denon_telnet_port`, que le cœur recopie depuis
`DEDUP_DENON_*` (spec 023, US3), sont repris dans `hote` et `port_telnet`.

Le réveil a besoin aussi du réglage **Réseau** d'unisson (`adresse_reseau`,
l'adresse que l'ampli peut joindre) : sans lui, aucune alarme ne part
(`adresse_reseau_non_reglee`), et le diagnostic montre le lien
`/admin/settings#reseau`. Sur l'ampli, régler « Contrôle réseau » sur
« Toujours activé » (sinon il ne répond plus en veille) et lui donner une IP
fixe.

## À confirmer en R0 (recette sur l'ampli)

Les valeurs du pilote `avrx4000` sont provisoires :

- ~~`source_reseau = "SINET"`~~ tranché le 2026-11-01 : `None`. `SINET`
  ouvre le menu réseau et coupe la lecture DLNA ; l'ampli bascule seul. Sans
  source forcée, la séance ne guette plus « autre source » par telnet (un
  `Stop` ou un autre média restent vus par UPnP) ;
- `delai_reveil_s = 8` : le temps de sortie de veille avant qu'un `Play`
  prenne, et si un `MV` ou un `SI` envoyé pendant ce temps est perdu (la
  séance les renvoie après le délai) ;
- `plafond = Plafond(frequence_max=96000, profondeur_max=24)` : le FLAC que
  l'ampli lit vraiment ;
- que `SetNextAVTransportURI` enchaîne, que `TrackURI` change au passage, et
  l'état (`STOPPED` ?) d'une fin de piste sans enchaînement : le repli n'est
  vérifié que contre le faux lecteur ;
- les états au réveil (`TRANSITIONING` puis `PLAYING`), le format de
  `RelTime` et `TrackDuration` pendant la lecture, la faute d'un `Play`
  envoyé en veille ;
- que l'ampli renvoie bien `MVxxx` après chaque pas de volume (sans écho, la
  montée ne sait pas qu'on y a touché, et va jusqu'au bout) ;
- et le relevé du lot 2 (`docs/reveil.md`, « À vérifier pendant la recette »).

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

Les faux sont posés à la frontière : un faux ampli TCP (qui renvoie l'écho
des commandes, comme un AVR), un vrai serveur HTTP qui joue un lecteur DLNA
à états (`tests/aides_seance.py` : `Play`, `RelTime` qui avance, `NextURI`
en fin de piste, `Stop` venu d'ailleurs, `SetNext` refusé…), la vraie
façade du cœur avec de vraies pistes en base et sur le disque, et une
horloge injectée dans l'ordonnanceur. La séance tourne avec des durées
courtes (`Cadence`). La migration est jouée dans
`plugin_denon` sur la base de test, et le schéma retiré après chaque test.
Le testeur de fuseau est éprouvé en temps réel : `dans_s = 5` doit partir
entre 5 et 6,5 s.
La non-régression de Hublot rejoue ses appels, puis exécute son vrai client
(`plugins/denon/plugin.js`) avec node contre l'écoute à part. Elle se saute
si node ou le dépôt Hublot manquent (`HUBLOT_SRC`, défaut `../hublot`).
