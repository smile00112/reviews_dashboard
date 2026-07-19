"""attention rules: configurable triggers for the overview attention feed

Revision ID: 0015_attention_rules
Revises: 0014_background_jobs
Create Date: 2026-07-18

Additive. Seeds 5 global enabled rules replicating the previously hardcoded
thresholds in DashboardService._attention, so dashboard behavior does not
change on deploy.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_attention_rules"
down_revision: Union[str, None] = "0014_background_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: types are created/dropped explicitly below (см. 0014).
rule_type_enum = postgresql.ENUM(
    "unanswered_overdue", "fresh_negative", "escalated", "rating_drop", "aspect_spike",
    name="attention_rule_type_enum", create_type=False,
)
severity_enum = postgresql.ENUM("urgent", "warn", "info", name="attention_severity_enum", create_type=False)
scope_enum = postgresql.ENUM("global", "company", "organizations", name="attention_scope_enum", create_type=False)

# Сиды = текущие захардкоженные пороги DashboardService._attention.
SEED_RULES = [
    ("unanswered_overdue", "urgent", {"hours": 24}),
    ("fresh_negative", "urgent", {"window_hours": 2, "max_rating": 2}),
    ("escalated", "warn", {}),
    ("rating_drop", "warn", {"threshold": -0.2, "top": 3}),
    ("aspect_spike", "warn", {"min_recent": 3, "top": 3}),
]


def upgrade() -> None:
    bind = op.get_bind()
    rule_type_enum.create(bind, checkfirst=True)
    severity_enum.create(bind, checkfirst=True)
    scope_enum.create(bind, checkfirst=True)

    table = op.create_table(
        "attention_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_type", rule_type_enum, nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("scope_type", scope_enum, nullable=False, server_default="global"),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("organization_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(), "rule_type": rule_type, "name": None,
                "is_enabled": True, "severity": severity, "params": params,
                "scope_type": "global", "company_id": None, "organization_ids": [],
            }
            for rule_type, severity, params in SEED_RULES
        ],
    )


def downgrade() -> None:
    op.drop_table("attention_rules")
    bind = op.get_bind()
    scope_enum.drop(bind, checkfirst=True)
    severity_enum.drop(bind, checkfirst=True)
    rule_type_enum.drop(bind, checkfirst=True)
