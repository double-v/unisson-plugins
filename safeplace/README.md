# Safeplace

Signaler des artistes (accusations, condamnations) et proposer de les mettre
à la corbeille. Plugin **officiel** d'unisson, **inactif par défaut** : signaler
un artiste est un choix personnel, pas une fonction de la bibliothèque. C'est
aussi l'exemple complet du guide des plugins (`docs/plugins.md` du cœur).

## Ce qu'il apporte

- **Table `artist_flags`** — une ligne par artiste (`artist_id` unique, clé vers
  `artists` en `ON DELETE CASCADE`) : `reasons`, `severity`
  (`accusé`|`condamné`|`autre`), `source_url`, `flagged_by` (`user`|`serge`),
  `flagged_at` (chaîne ISO), `pending_review` (1 = suggestion de l'assistant à
  valider). Elle vit dans le schéma du plugin, **`plugin_safeplace`**
  (cœur ≥ 0.3, un schéma par plugin) : la révision `5afe00000001` la crée sur
  une base neuve et l'**adopte en la déplaçant** (`SET SCHEMA`, sans copie)
  sur une base où le cœur l'avait créée ; `5afe00000002` déplace celle
  qu'une 1.1.x avait laissée dans `public`. Lignes, identifiants, index et
  clé vers `artists` suivent.
- **Routes** sous `/api/plugins/safeplace/` :
  `GET /flags` (`PageOut`, enrichi de `artist_name`, `genre_name`,
  `album_count`, `total_size_bytes` hors corbeille ; filtres `genre_id`,
  `severity`, `pending_review` seulement s'ils sont actifs, 422 sur une valeur
  inconnue), `GET /flags/{artist_id}` (`null` sans signalement),
  `POST /flags` (pose ou met à jour, 404 si l'artiste n'existe pas),
  `PUT /flags/{artist_id}/confirm`, `DELETE /flags/{artist_id}`.
- **Un outil de l'assistant** : `safeplace_check_artist_status` (lecture, nom
  rapproché à 80 ; rend l'`artist_id` d'un artiste de la bibliothèque pas
  encore signalé).
- **Une carte d'action dans le chat** (cœur ≥ 0.2, #931) : le type
  d'opération `safeplace.signaler`, proposé par `propose_action`. Valider la
  carte le tamponne ; l'appliquer pose un signalement **confirmé**
  (`flagged_by="carte"`), ou confirme une suggestion en attente sans
  réécrire ses motifs. Le révoquer ramène à l'état d'avant (retiré, ou de
  nouveau en attente) ; un signalement déjà acté, un artiste à la corbeille
  ou disparu sont rangés sans effet. La corbeille reste un geste à
  part, depuis la page. L'ancien `safeplace_suggest_addition`, qui écrivait
  sans passer par l'opérateur, est retiré.
- **Écrans (admin)** : une page « Safeplace » dans Extensions (en attente,
  liste filtrable, « Proposer la corbeille », « Retirer ») ; sur la fiche
  artiste, un badge « ⚑ Signalé » (`fiche-artiste.entete`), un bloc
  « Signalement » (`fiche-artiste.blocs`) et une carte « Signaler »
  (`fiche-artiste.hub`) ; dans le chat, le détail de la carte
  `safeplace.signaler` (`chat.carte-action`).
- **La corbeille reste au cœur** : « Proposer la corbeille » tamponne un
  `trash_artist` avec la provenance `safeplace`. Le plugin l'utilise, il ne le
  possède pas.

Un signalement ne touche à aucun fichier : il n'exige pas le mode édition.
Désactiver le plugin retire ses écrans, ses routes et ses outils ; les
signalements restent en base.

## Écrans

Sources dans `front/admin-src/`, compilées dans `front/admin/index.js` par le
préréglage Vite du gabarit (Vue et les primitives viennent de l'hôte) :

```sh
ln -s <checkout unisson>/frontend/node_modules node_modules   # ou npm install
./node_modules/.bin/vite build
```

## Tests

Ils tournent dans le harnais du cœur (sa base de test, son app, son chargeur),
depuis le checkout d'unisson :

```sh
PYTHONPATH=. TEST_DATABASE_URL=postgresql+asyncpg://dedup:dedup@localhost:5432/dedup_test \
  .venv/bin/python -m pytest <unisson-plugins>/safeplace/tests \
  -c backend/pyproject.toml --rootdir=backend -p backend.tests.conftest
```

L'adoption de la table (base neuve, base peuplée, bascule d'une 1.1.x) est
testée côté cœur (`backend/tests/test_adoption_artist_flags.py`) sur cette
chaîne-ci : `UNISSON_PLUGINS_SRC=<unisson-plugins>` la désigne.
