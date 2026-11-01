"""les alarmes du réveil

Une ligne par alarme (conception : `docs/reveil.md`, « Une alarme »). Le
chargeur joue la chaîne avec `search_path = plugin_denon, public` : sans
schéma, la table s'écrit chez le plugin.

Hors conception :
- `derniere_echeance` : l'occurrence traitée en dernier, partie ou manquée.
  C'est elle qui empêche un double départ, et `derniere_execution` moins
  elle donne le retard du départ ;
- `test` : l'alarme créée par le testeur de fuseau, supprimée après son
  passage.

Pas de clé étrangère vers `playlists`, `artists` ou `albums` : une alarme
dont le contexte disparaît ne doit pas disparaître avec lui, elle le dira
au déclenchement.

Revision ID: de0000000001
Revises:
Create Date: 2026-11-01 10:00:00.000000

"""
from alembic import op


revision = "de0000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE alarmes (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            heure VARCHAR(8) NOT NULL,
            jours INTEGER NOT NULL DEFAULT 0,
            contexte VARCHAR(20) NOT NULL,
            contexte_id INTEGER,
            melange BOOLEAN NOT NULL DEFAULT FALSE,
            genre_id INTEGER,
            format VARCHAR(10),
            favoris BOOLEAN NOT NULL DEFAULT FALSE,
            volume_depart_db REAL NOT NULL,
            volume_cible_db REAL NOT NULL,
            montee_s INTEGER NOT NULL DEFAULT 0,
            fin_mode VARCHAR(20) NOT NULL,
            fin_valeur INTEGER,
            test BOOLEAN NOT NULL DEFAULT FALSE,
            derniere_echeance VARCHAR,
            derniere_execution VARCHAR,
            dernier_resultat VARCHAR(40),
            cree_le VARCHAR NOT NULL,
            modifie_le VARCHAR NOT NULL
        )
        """
    )


def downgrade() -> None:
    # Désinstaller n'est pas purger : seule une purge explicite retire les
    # données d'un plugin (spec 018, FR-011).
    pass
