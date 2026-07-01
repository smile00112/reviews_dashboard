"""add public_http scrape mode (feature 003)

Revision ID: 0003_public_http_mode
Revises: 0002_review_analysis
Create Date: 2026-06-30

Note: migration 0001 created a single shared Postgres enum type ``scrape_mode_enum`` and
used it for organizations.preferred_scrape_mode, reviews.scrape_mode, and scrape_runs.mode
(the differing ``name=`` in the ORM models only affect non-Postgres/test backends, where
the value is stored as text). So only one ALTER TYPE is required here.

``ALTER TYPE ... ADD VALUE`` cannot execute inside a transaction block on some PostgreSQL
versions, so the value is added with autocommit.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_public_http_mode"
down_revision: Union[str, None] = "0002_review_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Postgres only; SQLite stores enums as text and needs no change.
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE scrape_mode_enum ADD VALUE IF NOT EXISTS 'public_http'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value; downgrade is a no-op.
    pass
