"""Add an active flag to organizations (branches).

false = точка исключена из автоматического сбора отзывов (nightly reviews job
и /scrape/all её пропускают).

Revision ID: 0026_organization_is_active
Revises: 0025_company_short_name
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_organization_is_active"
down_revision = "0025_company_short_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive, NOT NULL, server_default true: существующие точки остаются активными.
    op.add_column(
        "organizations",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "is_active")
