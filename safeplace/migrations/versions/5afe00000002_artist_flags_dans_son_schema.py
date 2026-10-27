"""artist_flags dans le schéma du plugin

Cœur ≥ 0.3 (spec 018, R2 bis) : chaque plugin a son schéma Postgres. Une base
passée par la 1.1.x a `artist_flags` dans `public` ; elle la **déplace** dans
`plugin_safeplace` (`SET SCHEMA` ne touche que le catalogue : lignes,
identifiants, séquence, index et clé vers `artists` suivent). Le chargeur du
cœur a déjà rangé la table de version dans le schéma avant cette révision.

Sur une base neuve ou déjà déplacée par `5afe00000001`, elle ne fait rien.

Revision ID: 5afe00000002
Revises: 5afe00000001
Create Date: 2026-10-27 18:00:00.000000

"""
from alembic import op


revision = "5afe00000002"
down_revision = "5afe00000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS public.artist_flags SET SCHEMA plugin_safeplace")


def downgrade() -> None:
    # Le cœur ne redescend pas une chaîne de plugin ; et `public` ne se
    # touche pas (FR-046).
    pass
