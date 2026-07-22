"""Add a short display name to companies (used in branch pickers).

Revision ID: 0025_company_short_name
Revises: 0024_roles_permissions
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_company_short_name"
down_revision = "0024_roles_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive, nullable, no backfill: NULL means "fall back to the full name".
    op.add_column("companies", sa.Column("short_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "short_name")
