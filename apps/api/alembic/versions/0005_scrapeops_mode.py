"""add scrapeops scrape mode (feature 005)

Revision ID: 0005_scrapeops_mode
Revises: 0004_admin_rbac
Create Date: 2026-07-01

Adds ``scrapeops`` value to the shared Postgres enum ``scrape_mode_enum``
(used by organizations.preferred_scrape_mode, reviews.scrape_mode, and
scrape_runs.mode). ``ALTER TYPE ... ADD VALUE`` cannot run inside a
transaction block on some PostgreSQL versions — added with autocommit.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_scrapeops_mode"
down_revision: Union[str, None] = "0004_admin_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Postgres only; SQLite stores enums as text and needs no change.
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE scrape_mode_enum ADD VALUE IF NOT EXISTS 'scrapeops'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value; downgrade is a no-op.
    pass
