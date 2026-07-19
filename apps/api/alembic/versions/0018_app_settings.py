"""app_settings key-value table (dashboard settings feature).

Additive. One row per scalar setting; absence means "use config default".

Revision ID: 0018_app_settings
Revises: 0017_overview_indexes
Create Date: 2026-07-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# NB: alembic_version.version_num is varchar(32) — keep this id short.
revision: str = "0018_app_settings"
down_revision: Union[str, None] = "0017_overview_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
