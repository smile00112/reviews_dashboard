"""multi-platform ratings (Yandex / 2GIS / Google) on organizations

Revision ID: 0010_multi_platform_metrics
Revises: 0009_nullable_org_url
Create Date: 2026-07-10

Additive: one organization can appear on three map platforms. Yandex keeps its
existing rating/review_count columns; we add its rating_count plus a full
url/rating/review_count/rating_count set for 2GIS and Google. All nullable.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_multi_platform_metrics"
down_revision: Union[str, None] = "0009_nullable_org_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("yandex_rating_count", sa.Integer(), nullable=True))
    op.add_column("organizations", sa.Column("gis2_url", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("gis2_rating", sa.Numeric(3, 2), nullable=True))
    op.add_column("organizations", sa.Column("gis2_review_count", sa.Integer(), nullable=True))
    op.add_column("organizations", sa.Column("gis2_rating_count", sa.Integer(), nullable=True))
    # google_url is already added by 0008_org_map_links (map-links branch); only the
    # extra google metric columns are new here.
    op.add_column("organizations", sa.Column("google_rating", sa.Numeric(3, 2), nullable=True))
    op.add_column("organizations", sa.Column("google_review_count", sa.Integer(), nullable=True))
    op.add_column("organizations", sa.Column("google_rating_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "google_rating_count")
    op.drop_column("organizations", "google_review_count")
    op.drop_column("organizations", "google_rating")
    op.drop_column("organizations", "gis2_rating_count")
    op.drop_column("organizations", "gis2_review_count")
    op.drop_column("organizations", "gis2_rating")
    op.drop_column("organizations", "gis2_url")
    op.drop_column("organizations", "yandex_rating_count")
