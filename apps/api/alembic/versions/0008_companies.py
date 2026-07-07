"""add companies parent table + organizations.company_id (feature 008)

Revision ID: 0008_companies
Revises: 0007_response_first_seen
Create Date: 2026-07-07

Additive: a ``companies`` parent groups organization branches by city.
``organizations`` stays the scrape/dedup unit — reviews, content_hash, and
uq_review_org_hash are untouched.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_companies"
down_revision: Union[str, None] = "0007_response_first_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column("organizations", sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_organizations_company_id",
        "organizations",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_organizations_company_id", "organizations", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_organizations_company_id", table_name="organizations")
    op.drop_constraint("fk_organizations_company_id", "organizations", type_="foreignkey")
    op.drop_column("organizations", "company_id")
    op.drop_table("companies")
