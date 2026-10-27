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
  valider). La révision `5afe00000001` la crée sur une base neuve et
  **l'adopte** telle quelle sur une base où le cœur l'avait créée.
- **Routes** sous `/api/plugins/safeplace/` :
  `GET /flags` (`PageOut`, enrichi de `artist_name`, `genre_name`,
  `album_count`, `total_size_bytes` hors corbeille ; filtres `genre_id`,
  `severity`, `pending_review` seulement s'ils sont actifs, 422 sur une valeur
  inconnue), `GET /flags/{artist_id}` (`null` sans signalement),
  `POST /flags` (pose ou met à jour, 404 si l'artiste n'existe pas),
  `PUT /flags/{artist_id}/confirm`, `DELETE /flags/{artist_id}`.
- **Deux outils de l'assistant** : `safeplace_check_artist_status` (lecture,
  nom rapproché à 80) et `safeplace_suggest_addition`, qui pose un signalement
  **en attente** (`flagged_by="serge"`, `pending_review=1`) sans jamais
  rétrograder un signalement acté. L'opérateur confirme ou rejette depuis la
  page.
- **Écrans (admin)** : une page « Safeplace » dans Extensions (en attente,
  liste filtrable, « Proposer la corbeille », « Retirer ») ; sur la fiche
  artiste, un badge « ⚑ Signalé » (`fiche-artiste.entete`), un bloc
  « Signalement » (`fiche-artiste.blocs`) et une carte « Signaler »
  (`fiche-artiste.hub`).
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

L'adoption de la table est testée côté cœur
(`backend/tests/test_adoption_artist_flags.py`), sur cette révision-ci.
