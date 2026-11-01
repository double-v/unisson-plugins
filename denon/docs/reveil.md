# Le réveil Denon — conception

Deuxième partie du plugin `denon` (unisson#343). Le premier lot, le
multiplexeur, tient la connexion telnet unique (`backend/lien.py`). Le réveil
s'appuie sur ce lien et sur le cœur 0.5 (spec 023, US1) : `ctx.flux_lecteur`,
`ctx.tirer_pistes`, `ctx.pistes_playlist`, `ctx.marquer_jouee`,
`ctx.adresse_reseau`. Contrat : `specs/023-flux-lecteurs-reseau/contracts/facade-plugin.md`
dans le dépôt du cœur.

## Décisions de l'opérateur (2026-11-01)

- **Volume** : une montée douce, d'un volume de départ vers un volume cible,
  sur une durée. Les trois se règlent par alarme.
- **Fin** : un mode par alarme. Après une durée (puis veille de l'ampli),
  après un nombre de pistes (puis veille), ou sans limite (le tirage se
  relance jusqu'à ce que quelqu'un arrête).
- **Ampli occupé** (allumé sur la TV, un jeu) : l'alarme **prend la main**.
- **Ce qui se joue** : une playlist (dans l'ordre ou mélangée), ou un tirage
  dans les contextes de l'aléatoire du player (bibliothèque avec filtres
  genre, format, favoris ; un artiste ; un album). Décidé dans la spec 023.

## Une alarme

Table `plugin_denon.alarmes` (migration du plugin, dans son schéma) :

| Colonne | Type | Rôle |
|---|---|---|
| `id` | int | |
| `nom` | str | « Semaine », « Week-end » |
| `active` | bool | |
| `heure` | str `HH:MM` | heure locale (réglage `fuseau`) |
| `jours` | int | masque : lundi = 1, mardi = 2, … dimanche = 64 ; 0 = une seule fois |
| `contexte` | str | `playlist`, `bibliotheque`, `artiste`, `album` |
| `contexte_id` | int ou null | |
| `melange` | bool | playlist seulement : ordre ou mélange |
| `genre_id`, `format`, `favoris` | | filtres, contexte `bibliotheque` seulement |
| `volume_depart_db`, `volume_cible_db` | float | -80 à 18 |
| `montee_s` | int | 0 à 3600 (1 h au plus) ; 0 = volume cible d'emblée |
| `fin_mode` | str | `duree`, `pistes`, `sans_limite` |
| `fin_valeur` | int ou null | minutes, ou nombre de pistes |
| `derniere_execution` | str ISO | empêche un double déclenchement |
| `dernier_resultat` | str | code (`joue`, `ampli_injoignable`, `adresse_reseau_non_reglee`…) |
| `cree_le`, `modifie_le` | str ISO | |

Une alarme à `jours = 0` se désactive après son passage.

Réglages ajoutés au plugin : `fuseau` (défaut `Europe/Paris`) et
`hote_upnp` (vide : l'hôte telnet, port 8080).

## Le déclenchement

Une tâche de fond calcule la prochaine occurrence de toutes les alarmes
actives, dans le fuseau réglé, et **dort jusqu'à elle** (30 s au plus, et
réveillée tout de suite par toute écriture d'alarme). Une alarme part si son
occurrence est passée et que `derniere_execution` est antérieure. La
précision visée est d'environ une seconde, pour que le testeur de 5 s ait un
sens. L'heure `HH:MM:SS` est acceptée (secondes à 0 par défaut).
**Rattrapage** : si unisson redémarre jusqu'à 10 minutes après l'heure,
l'alarme part en retard ; au-delà, elle est notée `manquee`, et elle ne part
pas.

## La séance

Une seule séance à la fois. Une alarme qui part pendant une séance la
remplace.

1. **Allumer** : `PWON` par le lien, puis le volume de départ (`MV`), puis la
   source réseau du pilote si R0 montre que l'ampli ne bascule pas seul
   (`SINET` sur l'AVR-X4000, à confirmer). On prend la main quelle que soit
   la source.
2. **Attendre que l'ampli soit prêt** : `GetTransportInfo` répond déjà en
   veille, il ne prouve donc rien. On attend le délai de sortie de veille
   mesuré en R0 (pilote : `delai_reveil_s`), puis on réessaie `Play` jusqu'à
   `PLAYING`, 3 essais au plus.
3. **Les pistes** : `pistes_playlist` (mélangée si demandé) ou
   `tirer_pistes(n=…)`. En mode `pistes`, on en prend `fin_valeur` ; sinon un
   lot de 50, relancé quand il s'épuise en `sans_limite`.
4. **Les formats** : `GetProtocolInfo` du lecteur, une fois par séance, et le
   plafond du pilote (`Plafond`, mesuré en R0).
5. **Jouer** : `flux_lecteur(piste)` → `SetAVTransportURI` avec le DIDL-Lite
   (titre, artiste, album, pochette, `protocol_info`) → `Play` →
   `marquer_jouee`. La suivante est mise en attente par
   `SetNextAVTransportURI`.
6. **Suivre** (toutes les 2 s, `GetPositionInfo` et `GetTransportInfo`) :
   quand `TrackURI` passe à la suivante, `marquer_jouee` puis on met en
   attente celle d'après. Une piste dont le flux est impossible
   (`FluxImpossible`) est sautée et journalisée.
7. **Monter le volume** : de `volume_depart_db` à `volume_cible_db` sur
   `montee_s`, par pas de 0,5 dB envoyés par le lien. **La montée s'arrête
   si quelqu'un touche au volume** : l'état poussé par l'ampli diffère alors
   du dernier pas envoyé.
8. **Finir** :
   - `duree` : à l'échéance, `Stop` puis `PWSTANDBY` ;
   - `pistes` : après la dernière, `PWSTANDBY` ;
   - `sans_limite` : jamais tout seul.

   **Quelqu'un reprend la main** pendant la séance (autre source, `Stop` ou
   `Pause` venus d'ailleurs) : la séance s'arrête, sans mise en veille.

Chaque étape est journalisée (`unisson.plugin.denon`), et le résultat va
dans `dernier_resultat`.

## Le testeur de fuseau (demande de l'opérateur)

« Tester dans 5 s » et « Tester dans 10 s » : le serveur prend l'heure
actuelle **dans le fuseau réglé**, y ajoute 5 ou 10 s, et crée une alarme
unique (`jours = 0`, nom « Test 07:42:15 ») avec les réglages de son choix
(par défaut : la première alarme, sinon un tirage de la bibliothèque, volume
bas, fin après 1 piste). Elle passe par le **vrai ordonnanceur**, pas par
`essayer`. Si elle part à l'heure, le fuseau et l'horloge sont bons. La
réponse et le diagnostic montrent côte à côte :

- l'heure du serveur dans le fuseau réglé, avec son décalage (`+01:00`) ;
- l'heure UTC du serveur ;
- l'heure du navigateur, et l'écart avec celle du serveur. Au-delà de 1 min,
  un avertissement : « l'horloge ou le fuseau du serveur ne correspond pas ».

Le résultat (parti à l'heure prévue, avec quel retard) s'affiche sur la
ligne de l'alarme de test, qui se supprime toute seule après son passage.

## Les routes (sous `/api/plugins/denon/`, protégées par le jeton)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/reveil/alarmes` | liste, avec la prochaine occurrence |
| POST | `/reveil/alarmes` | créer (validation : heure, jours, volumes, fin, contexte existant) |
| PUT | `/reveil/alarmes/{id}` | modifier |
| DELETE | `/reveil/alarmes/{id}` | supprimer |
| POST | `/reveil/alarmes/{id}/essayer` | lancer la séance maintenant |
| POST | `/reveil/tester` | `{dans_s: 5 \| 10, alarme_id?}` : crée l'alarme de test, rend les heures serveur, UTC et l'échéance |
| GET | `/reveil/horloge` | heure du serveur dans le fuseau, décalage, UTC |
| GET | `/reveil/seance` | séance en cours : alarme, piste, volume, fin prévue |
| POST | `/reveil/seance/arreter` | arrêter (sans mise en veille) |
| GET | `/reveil/diagnostic` | telnet connecté, UPnP joignable, adresse réseau réglée, formats annoncés, conseils (contrôle réseau en veille, IP fixe) |

## Les écrans (admin, page « Réveil » dans Extensions)

La liste des alarmes (prochaine occurrence, dernier résultat), le formulaire
d'une alarme, la séance en cours avec « Arrêter », le diagnostic.

**Prototype validé par l'opérateur le 2026-11-01** (`proto-reveil.html`, à côté), avec ces choix :
http://192.168.1.116:8101/unisson-plugins/denon-reveil/index.html

- le formulaire s'ouvre sur une page à part (« ‹ Réveil » pour revenir) ;
- la durée de montée se règle par un curseur, avec des presets de 2, 5, 10
  et 15 min, jusqu'à 1 h ; une petite courbe dessine la montée ;
- un avertissement s'affiche quand le volume cible dépasse -15 dB (« fort
  pour un réveil ») ;
- le résultat du testeur apparaît à deux endroits : la ligne « Test
  HH:MM:SS » reste 60 s dans la liste, et le dernier résultat reste dans la
  carte « L'heure » du diagnostic jusqu'au test suivant ;
- l'écart d'horloge précise « comparé à l'heure de ce navigateur
  (<fuseau>) » ;
- une pastille rouge sur l'onglet Diagnostic quand quelque chose ne va pas.

Le lien vers le réglage de l'adresse réseau (`AdresseReseauNonReglee.reglage`
vaut `/settings#reseau`) se préfixe de `/admin`, où l'admin est servie.

## Les lots

| Lot | Contenu | Dépend de |
|---|---|---|
| 2 | `backend/dlna.py` : client UPnP (description, `GetProtocolInfo`, AVTransport, DIDL-Lite) | — |
| 3 | alarmes : migration, modèle, validation, routes CRUD, calcul de la prochaine occurrence, ordonnanceur (sans séance), testeur de fuseau et horloge | — |
| 4 | la séance (déroulé ci-dessus), `essayer`, `seance`, `arreter`, `diagnostic` | 2, 3, cœur 0.5 |
| 5 | les écrans | prototype validé, 3, 4 |
| R0 | recette sur l'ampli : délai de réveil, plafond FLAC, source réseau | l'opérateur |

## À vérifier pendant la recette (relevé des lots 2 et US1)

- l'ampli accepte-t-il notre DIDL sans `dlna:profileID` sur la pochette
  (Jellyfin met `JPEG_SM`) ;
- `SetNextAVTransportURI` enchaîne-t-il les pistes, et `TrackURI` change-t-il
  au passage ;
- les codes de faute d'un format refusé (714 ?) et d'un `Play` envoyé en
  veille ;
- les états au réveil (`TRANSITIONING` puis `PLAYING`) et le format de
  `TrackDuration` pendant la lecture ;
- `OP=01` sur un flux `CI=1`, le suffixe d'extension dans l'URL, la forme du
  `Range`, la reprise après pause, une sonde en `HEAD`, HTTP/1.0 ou 1.1 ;
- le plafond FLAC réel et le délai de sortie de veille.
