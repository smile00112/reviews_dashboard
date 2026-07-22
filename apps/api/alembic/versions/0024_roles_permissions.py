"""configurable roles & permissions (feature 016)

Creates roles + role_permissions, seeds admin/call_center/manager with their
default grants, adds users.role_id (backfilled from the legacy users.role enum),
and makes the legacy users.role column nullable (retained for rollback).

Revision ID: 0024_roles_permissions
Revises: 0023_attention_events_and_lifecycle
Create Date: 2026-07-22
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.permissions import DEFAULT_ROLES, LEGACY_ROLE_MAP

revision: str = "0024_roles_permissions"
down_revision: Union[str, None] = "0023_attention_events_and_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- tables --------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_role_name"),
        sa.UniqueConstraint("slug", name="uq_role_slug"),
    )
    op.create_index("ix_roles_slug", "roles", ["slug"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission", sa.Text(), nullable=False),
        sa.UniqueConstraint("role_id", "permission", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])

    # --- seed roles + grants -------------------------------------------------
    roles_tbl = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.Text),
        sa.column("slug", sa.Text),
        sa.column("is_system", sa.Boolean),
        sa.column("description", sa.Text),
    )
    grants_tbl = sa.table(
        "role_permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission", sa.Text),
    )

    slug_to_id: dict[str, uuid.UUID] = {}
    role_rows = []
    grant_rows = []
    for spec in DEFAULT_ROLES:
        rid = uuid.uuid4()
        slug_to_id[spec["slug"]] = rid
        role_rows.append(
            {
                "id": rid,
                "name": spec["name"],
                "slug": spec["slug"],
                "is_system": spec["is_system"],
                "description": spec.get("description"),
            }
        )
        for perm in spec["grants"]:
            grant_rows.append({"id": uuid.uuid4(), "role_id": rid, "permission": perm})

    op.bulk_insert(roles_tbl, role_rows)
    if grant_rows:
        op.bulk_insert(grants_tbl, grant_rows)

    # --- users.role_id (nullable → backfill → NOT NULL) ----------------------
    op.add_column(
        "users",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    for legacy_value, slug in LEGACY_ROLE_MAP.items():
        # role is a Postgres enum; cast to text for comparison against the literal.
        op.execute(
            sa.text("UPDATE users SET role_id = :rid WHERE role::text = :legacy").bindparams(
                rid=slug_to_id[slug], legacy=legacy_value
            )
        )
    # Any user whose legacy role is unknown/NULL falls back to call_center so no
    # account is left role-less (FR-005).
    op.execute(
        sa.text("UPDATE users SET role_id = :rid WHERE role_id IS NULL").bindparams(
            rid=slug_to_id[LEGACY_ROLE_MAP["review_operator"]]
        )
    )
    op.alter_column("users", "role_id", nullable=False)
    op.create_index("ix_users_role_id", "users", ["role_id"])

    # --- legacy users.role → nullable (retained for rollback) ----------------
    op.alter_column("users", "role", existing_type=postgresql.ENUM(name="user_role_enum"), nullable=True)


def downgrade() -> None:
    # Restore users.role from the role slug where possible, then drop the new bits.
    slug_to_legacy = {v: k for k, v in LEGACY_ROLE_MAP.items()}
    for slug, legacy_value in slug_to_legacy.items():
        op.execute(
            sa.text(
                "UPDATE users SET role = :legacy "
                "WHERE role_id IN (SELECT id FROM roles WHERE slug = :slug)"
            ).bindparams(legacy=legacy_value, slug=slug)
        )
    op.alter_column("users", "role", existing_type=postgresql.ENUM(name="user_role_enum"), nullable=False)

    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_column("users", "role_id")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_roles_slug", table_name="roles")
    op.drop_table("roles")
