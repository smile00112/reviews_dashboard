"""Record why a login ended and how it got there.

Revision ID: 0021_session_login_progress
Revises: 0020_session_unique_provider
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_session_login_progress"
down_revision = "0020_session_unique_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scraper_sessions", sa.Column("last_message", sa.Text(), nullable=True))
    op.add_column("scraper_sessions", sa.Column("progress", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("scraper_sessions", "progress")
    op.drop_column("scraper_sessions", "last_message")
