"""add reviews.response_first_seen_at (feature 007)

Revision ID: 0007_response_first_seen
Revises: 0006_twogis_api_mode
Create Date: 2026-07-06

Records the observation-time proxy for when a business response first appeared on
a review. Nullable, no server default, no backfill — historical rows stay NULL
because we genuinely never observed their first-response time. Never feeds the
deduplication content_hash.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_response_first_seen"
down_revision: Union[str, None] = "0006_twogis_api_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column("response_first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reviews", "response_first_seen_at")
