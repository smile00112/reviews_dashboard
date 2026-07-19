"""Review removal tracking: reviews.removed_at + scrape_runs.full_pass (feature 011).

Additive only. removed_at NULL = review is currently present on the platform;
existing rows therefore start as "present" with no backfill. full_pass defaults
to false, so historical runs correctly read as partial coverage.

Revision ID: 0016_review_removal
Revises: 0015_attention_rules
Create Date: 2026-07-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# NB: alembic_version.version_num is varchar(32) — keep this id short.
revision: str = "0016_review_removal"
down_revision: Union[str, None] = "0015_attention_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "scrape_runs",
        sa.Column("full_pass", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("scrape_runs", "full_pass")
    op.drop_column("reviews", "removed_at")
