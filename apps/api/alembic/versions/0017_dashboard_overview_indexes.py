"""Dashboard overview aggregate indexes (feature 012).

Additive only. Supports the SQL-side overview aggregation:
- partial index on unanswered reviews (response_text IS NULL) for unanswered
  counters and per-organization unanswered counts;
- composite (organization_id, platform, first_seen_at) for platform-filtered
  period scans.

Revision ID: 0017_overview_indexes
Revises: 0016_review_removal
Create Date: 2026-07-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# NB: alembic_version.version_num is varchar(32) — keep this id short.
revision: str = "0017_overview_indexes"
down_revision: Union[str, None] = "0016_review_removal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_reviews_org_unanswered",
        "reviews",
        ["organization_id"],
        postgresql_where=sa.text("response_text IS NULL"),
    )
    op.create_index(
        "ix_reviews_org_platform_first_seen",
        "reviews",
        ["organization_id", "platform", "first_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reviews_org_platform_first_seen", table_name="reviews")
    op.drop_index("ix_reviews_org_unanswered", table_name="reviews")
