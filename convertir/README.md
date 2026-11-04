# convertir — WMA → MP3 tagué

Un WMA à 192 kbps sans tags vaut moins qu'un MP3 au même débit qu'on peut
nommer, taguer et retrouver (#950). Ce plugin réencode les **WMA avec perte**
d'un album en MP3, recopie leurs tags, et laisse le cœur poser les MP3 et
mettre les WMA à la corbeille. L'album rentre ensuite dans le circuit normal :
retagage sûr, renommage, « Corriger ».

Demande le cœur **≥ 0.8** (`ctx.remplacer_pistes`) et `ffmpeg`/`ffprobe` sur
le serveur (déjà dans l'image d'unisson).

## Ce qu'il fait

- **Une opération `convertir.mp3`** (cible : un album), qui passe par le
  tampon et le mode édition, **jamais par l'envoi automatique** (un encodage
  d'album prend des minutes, il s'approuve). Tout ou rien : les MP3 sont
  préparés dans un dossier temporaire, contrôlés, puis posés à côté des WMA,
  qui partent à la corbeille. Une erreur n'importe où laisse l'album intact.
- **Révocable** depuis l'historique : les MP3 vont à la corbeille, les WMA
  reviennent, avec leurs lignes, favoris et playlists.
- **Une carte « Convertir en MP3 »** dans le hub de la fiche album, avec
  l'aperçu : chaque piste, son nom MP3, le débit source → cible, ce qui part à
  la corbeille, ce qui est gardé et pourquoi.
- **Un outil « Convertir… »** au bout des lignes de la page qualité, qui ouvre
  le même aperçu.
- Après l'application (et la révocation), le cœur enfile un **scan ciblé** de
  l'album : les MP3 ont leurs lignes sans attendre l'auto-scan.

## Décisions (questions ouvertes de #950)

- **Formats** : les WMA avec perte (`wmav1`, `wmav2`, `wmapro`, `wmavoice`).
  Le **WMA Lossless** est gardé (motif `sans_perte`) : le passer en MP3
  jetterait une copie sans perte ; une conversion vers FLAC serait un autre
  type d'opération. RealAudio n'est pas lu par le scanner : rien à proposer.
  AAC, Ogg et Opus se taguent déjà.
- **Débit** : CBR, au **premier palier MP3 au moins égal à la source**
  (160 → 160, 193 → 224, 320 au plus ; 192 si la source est inconnue). Pas de
  réglage : remonter au-dessus ne rend rien de ce que le WMA a jeté, et
  descendre perdrait encore. Le contrôle relit le MP3 : débit, durée (± 1 s),
  et tous les tags écrits.
- **Tags** : les noms ASF que lit le scanner (#504) → ID3v2.4 (titre,
  artiste, album, artiste de l'album, piste, disque, année, genre,
  compositeur, éditeur, ISRC, identifiants MusicBrainz en `TXXX` et `UFID`,
  pochette `WM/Picture` → `APIC`). Ce qui n'a pas de cadre connu reste dans
  l'original, à la corbeille.
- **Lidarr** n'est pas prévenu : il reconstate au prochain rafraîchissement
  de l'artiste. Le piloter seul serait un geste sur un service externe, à
  décider à part.

## Refus

L'opération finit `failed` avec son motif, sans rien toucher : `perime`
(l'album a changé depuis l'aperçu), `ffmpeg_absent`, `encodage` ou
`controle` (le MP3 produit n'est pas conforme), et ceux du cœur
(`place_prise`, `fichier_absent`, `scan_en_cours`…). Sans mode édition, rien
n'est encodé.

## Écrans

```sh
npm install && npm run build   # → front/admin/index.js (committé)
```

## Tests

Depuis un checkout d'unisson (cœur ≥ 0.8), avec ffmpeg :

```sh
PYTHONPATH=. TEST_DATABASE_URL=… python -m pytest ../unisson-plugins/convertir/tests \
  -c backend/pyproject.toml --rootdir=backend -p backend.tests.conftest
```

Les WMA de test sont de vrais fichiers (ffmpeg, `wmav2`) tagués en ASF.
