"""add organizations.twogis_url and google_url (feature 008)

Revision ID: 0008_org_map_links
Revises: 0007_response_first_seen
Create Date: 2026-07-09

Adds two additive, nullable link columns so a single point (one ``organizations``
row) can carry its 2GIS and Google Maps links alongside the primary Yandex link.
Display/reference only: they never feed the scrape URL (``ScrapeService`` still
scrapes ``yandex_url``) or the deduplication content_hash.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_org_map_links"
down_revision: Union[str, None] = "0007_response_first_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("twogis_url", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("google_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "google_url")
    op.drop_column("organizations", "twogis_url")
