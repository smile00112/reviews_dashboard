"""add admin panel: User table + org/review columns (feature 004)

Revision ID: 0004_admin_rbac
Revises: 0003_public_http_mode
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_admin_rbac"
down_revision: Union[str, None] = "0003_public_http_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reference-only enums: no values list, create_type=False → SQLAlchemy never emits CREATE TYPE.
# Types are created via raw DDL below (supports IF NOT EXISTS).
_user_role = postgresql.ENUM(name="user_role_enum", create_type=False)
_review_status = postgresql.ENUM(name="review_status_enum", create_type=False)
_review_platform = postgresql.ENUM(name="review_platform_enum", create_type=False)


def upgrade() -> None:
    # Create enum types idempotently. PostgreSQL has no CREATE TYPE IF NOT EXISTS;
    # DO block catches duplicate_object and continues.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role_enum AS ENUM ('admin', 'review_operator');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE review_status_enum AS ENUM ('new', 'in_progress', 'answered', 'escalated');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE review_platform_enum AS ENUM ('yandex', 'google', 'gis2');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", _user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "default_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("avatar_initials", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # organizations — additive columns
    op.add_column("organizations", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("region", sa.Text(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("is_franchise", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # reviews — additive columns
    op.add_column("reviews", sa.Column("status", _review_status, nullable=True))
    op.add_column("reviews", sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("reviews", sa.Column("platform", _review_platform, nullable=True))
    op.add_column("reviews", sa.Column("paid_cost", sa.Integer(), nullable=True))
    op.add_column(
        "reviews",
        sa.Column(
            "paid_marked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("reviews", sa.Column("reply_text", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("reply_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "reviews",
        sa.Column(
            "replied_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # reviews
    op.drop_column("reviews", "replied_by_user_id")
    op.drop_column("reviews", "reply_at")
    op.drop_column("reviews", "reply_text")
    op.drop_column("reviews", "paid_marked_by_user_id")
    op.drop_column("reviews", "paid_cost")
    op.drop_column("reviews", "platform")
    op.drop_column("reviews", "is_paid")
    op.drop_column("reviews", "status")

    # organizations
    op.drop_column("organizations", "is_franchise")
    op.drop_column("organizations", "region")
    op.drop_column("organizations", "city")

    # users
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # enum types
    op.execute("DROP TYPE IF EXISTS review_platform_enum")
    op.execute("DROP TYPE IF EXISTS review_status_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
