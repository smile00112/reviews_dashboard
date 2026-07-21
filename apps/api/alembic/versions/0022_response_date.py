"""Store the real publication date of a scraped business reply.

Revision ID: 0022_response_date
Revises: 0021_session_login_progress
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_response_date"
down_revision = "0021_session_login_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive, nullable, no backfill: pre-existing rows keep NULL until re-scraped.
    op.add_column("reviews", sa.Column("response_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "response_date")
