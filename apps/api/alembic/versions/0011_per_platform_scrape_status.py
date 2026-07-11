"""per-platform scrape status/timestamp; drop shared last_scrape_status

Revision ID: 0011_per_platform_scrape_status
Revises: 0010_multi_platform_metrics
Create Date: 2026-07-11

The single last_scrape_status / last_successful_scrape_at could not express that an
org was scraped OK on one platform but not the other. Replace them with per-platform
columns (yandex_*, gis2_*). Backfill from existing data: a platform is 'success' where
its rating is present, else 'pending'; its timestamp inherits the old shared value.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_per_platform_scrape_status"
down_revision: Union[str, None] = "0010_multi_platform_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

org_status_enum = postgresql.ENUM(
    "pending", "running", "success", "failed", "needs_manual_action",
    name="org_scrape_status_enum", create_type=False,
)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("yandex_scrape_status", org_status_enum, nullable=False, server_default="pending"),
    )
    op.add_column(
        "organizations",
        sa.Column("gis2_scrape_status", org_status_enum, nullable=False, server_default="pending"),
    )
    op.add_column(
        "organizations",
        sa.Column("yandex_last_successful_scrape_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("gis2_last_successful_scrape_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill from the data already collected.
    op.execute(
        "UPDATE organizations SET yandex_scrape_status = 'success', "
        "yandex_last_successful_scrape_at = last_successful_scrape_at "
        "WHERE rating IS NOT NULL"
    )
    op.execute(
        "UPDATE organizations SET gis2_scrape_status = 'success', "
        "gis2_last_successful_scrape_at = last_successful_scrape_at "
        "WHERE gis2_rating IS NOT NULL"
    )

    op.drop_column("organizations", "last_scrape_status")
    op.drop_column("organizations", "last_successful_scrape_at")


def downgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("last_successful_scrape_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("last_scrape_status", org_status_enum, nullable=False, server_default="pending"),
    )
    # Best-effort restore: success if either platform succeeded.
    op.execute(
        "UPDATE organizations SET last_scrape_status = 'success' "
        "WHERE yandex_scrape_status = 'success' OR gis2_scrape_status = 'success'"
    )
    op.execute(
        "UPDATE organizations SET last_successful_scrape_at = "
        "GREATEST(yandex_last_successful_scrape_at, gis2_last_successful_scrape_at)"
    )

    op.drop_column("organizations", "gis2_last_successful_scrape_at")
    op.drop_column("organizations", "yandex_last_successful_scrape_at")
    op.drop_column("organizations", "gis2_scrape_status")
    op.drop_column("organizations", "yandex_scrape_status")
