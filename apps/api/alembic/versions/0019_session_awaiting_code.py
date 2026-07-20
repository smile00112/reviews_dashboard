"""session_status 'awaiting_code' value + scraper_sessions.pending_code
(Yandex password+confirmation-code login).

Additive only. ``ALTER TYPE ... ADD VALUE`` is irreversible on PostgreSQL —
the downgrade drops the column but leaves the enum value in place (harmless).

Revision ID: 0019_session_awaiting_code
Revises: 0018_app_settings
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# NB: alembic_version.version_num is varchar(32) — keep this id short.
revision: str = "0019_session_awaiting_code"
down_revision: Union[str, None] = "0018_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE session_status_enum ADD VALUE IF NOT EXISTS 'awaiting_code'")
    op.add_column("scraper_sessions", sa.Column("pending_code", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scraper_sessions", "pending_code")
    # session_status_enum 'awaiting_code' intentionally not removed (see docstring).
