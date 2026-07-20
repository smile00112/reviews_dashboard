"""Deduplicate scraper_sessions and enforce one row per provider.

Duplicate provider rows made `_get_or_create_session_record()`'s unordered
`.first()` non-deterministic: the request marked one row `pending` while the
background login terminalized another, stranding the UI on
"Выполняется вход…" forever.

Revision ID: 0020_session_unique_provider
Revises: 0019_session_awaiting_code
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_session_unique_provider"
down_revision = "0019_session_awaiting_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the most recently updated row per provider; the older duplicates
    # carry nothing worth preserving (status is re-derived on the next check).
    op.execute(
        sa.text(
            """
            DELETE FROM scraper_sessions a
            USING scraper_sessions b
            WHERE a.provider = b.provider
              AND (a.updated_at, a.id) < (b.updated_at, b.id)
            """
        )
    )
    op.create_unique_constraint("uq_scraper_sessions_provider", "scraper_sessions", ["provider"])


def downgrade() -> None:
    op.drop_constraint("uq_scraper_sessions_provider", "scraper_sessions", type_="unique")
