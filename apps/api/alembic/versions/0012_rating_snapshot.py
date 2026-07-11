"""daily rating_snapshot per organization/platform (feature 009)

Revision ID: 0012_rating_snapshot
Revises: 0011_per_platform_scrape_status
Create Date: 2026-07-11

Additive. Captures an organization's rating + review_count per platform once per
day so the network overview can compute period-over-period rating deltas. One row
per (organization, platform, captured_on); same-day capture upserts. Reuses the
existing ``review_platform_enum`` type. Never participates in review dedup.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_rating_snapshot"
down_revision: Union[str, None] = "0011_per_platform_scrape_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

platform_enum = postgresql.ENUM(
    "yandex", "google", "gis2", name="review_platform_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "rating_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", platform_enum, nullable=False),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "platform", "captured_on", name="uq_rating_snapshot_org_platform_day"
        ),
    )
    op.create_index("ix_rating_snapshot_organization_id", "rating_snapshot", ["organization_id"])
    op.create_index("ix_rating_snapshot_org_captured_on", "rating_snapshot", ["organization_id", "captured_on"])


def downgrade() -> None:
    op.drop_index("ix_rating_snapshot_org_captured_on", table_name="rating_snapshot")
    op.drop_index("ix_rating_snapshot_organization_id", table_name="rating_snapshot")
    op.drop_table("rating_snapshot")
