"""make organizations.yandex_url / normalized_url nullable

Revision ID: 0009_nullable_org_url
Revises: 0008_companies
Create Date: 2026-07-10

Additive: URL-less branches (rows imported from companies_data.csv without a
valid Yandex Maps URL) are stored with NULL yandex_url/normalized_url.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_nullable_org_url"
down_revision: Union[str, None] = "0008_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("organizations", "yandex_url", existing_type=sa.Text(), nullable=True)
    op.alter_column("organizations", "normalized_url", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("organizations", "normalized_url", existing_type=sa.Text(), nullable=False)
    op.alter_column("organizations", "yandex_url", existing_type=sa.Text(), nullable=False)
