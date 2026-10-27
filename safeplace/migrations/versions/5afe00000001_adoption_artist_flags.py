"""adoption de artist_flags

La table a longtemps appartenu au cœur (révision f7a1b2c3d4e5, désormais
vide). Sur une base qui l'a déjà, cette révision ne recrée rien et ne touche
à aucune ligne : elle l'**adopte**. Sur une base neuve, elle la crée, à
l'identique de ce que le cœur créait.

Depuis la 1.2.0 (cœur ≥ 0.3, un schéma par plugin), adopter, c'est
**déplacer** : la table quitte `public` pour `plugin_safeplace`, sans copie.
Une base qui avait déjà passé cette révision en 1.1.x est rattrapée par
`5afe00000002`.

Revision ID: 5afe00000001
Revises:
Create Date: 2026-10-27 15:00:00.000000

"""
from alembic import op


revision = "5afe00000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Le chargeur fait tourner la chaîne avec `search_path = plugin_safeplace,
    # public` : sans schéma, la table s'écrit chez le plugin.
    op.execute("ALTER TABLE IF EXISTS public.artist_flags SET SCHEMA plugin_safeplace")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS artist_flags (
            id SERIAL PRIMARY KEY,
            artist_id INTEGER NOT NULL REFERENCES public.artists(id) ON DELETE CASCADE,
            reasons TEXT NOT NULL DEFAULT '',
            severity VARCHAR(20) NOT NULL DEFAULT 'autre',
            source_url TEXT,
            flagged_by VARCHAR(20) NOT NULL DEFAULT 'user',
            flagged_at VARCHAR NOT NULL,
            pending_review INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_artist_flags_artist_id ON artist_flags (artist_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_artist_flags_severity ON artist_flags (severity)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_artist_flags_flagged_at ON artist_flags (flagged_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_artist_flags_pending_review ON artist_flags (pending_review)")


def downgrade() -> None:
    # Désinstaller n'est pas purger : seule une purge explicite retire les
    # données d'un plugin (spec 018, FR-011).
    pass
