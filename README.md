# unisson-plugins

Le catalogue officiel des plugins d'[unisson](https://github.com/double-v/unisson).

| Plugin | Ce qu'il fait |
|---|---|
| [`safeplace`](safeplace/) | Signaler des artistes et proposer de les mettre à la corbeille. Exemple complet du guide. |

Un plugin se dépose dans `DEDUP_PLUGINS_DIR` (défaut `data/plugins`) puis
s'active depuis la page **Plugins** de l'admin. Écrire le sien : partir du
gabarit (`outils/plugin/unisson_plugin.py nouveau <id>` dans le dépôt du cœur)
et suivre `docs/plugins.md`.
