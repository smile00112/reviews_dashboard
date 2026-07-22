"""attention rules cron model: lifecycle columns + attention_events

Revision ID: 0023_attention_events_and_lifecycle
Revises: 0022_response_date
Create Date: 2026-07-22

Feature 015. Additive. Turns attention rules stateful:
- attention_rules gains period_days / window_started_at / latched_at.
- New attention_events table stores per-firing snapshots (history + the live
  /overview block, which no longer computes anything on page load).

Reuses the existing PG enum types attention_rule_type_enum / attention_severity_enum
(created in 0015) for the event columns, so no new type is defined here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_attention_events_and_lifecycle"
down_revision: Union[str, None] = "0022_response_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: types already exist (migration 0015).
rule_type_enum = postgresql.ENUM(
    "unanswered_overdue", "fresh_negative", "escalated", "rating_drop", "aspect_spike",
    name="attention_rule_type_enum", create_type=False,
)
severity_enum = postgresql.ENUM(
    "urgent", "warn", "info", name="attention_severity_enum", create_type=False
)


def upgrade() -> None:
    # --- lifecycle columns on attention_rules --------------------------------
    op.add_column(
        "attention_rules",
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "attention_rules",
        sa.Column(
            "window_started_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.add_column(
        "attention_rules",
        sa.Column("latched_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing rows: anchor the first period at their creation time so the first
    # sweep evaluates them over [created_at, now] instead of a bogus future window.
    op.execute("UPDATE attention_rules SET window_started_at = created_at")

    # --- attention_events -----------------------------------------------------
    op.create_table(
        "attention_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attention_rules.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", rule_type_enum, nullable=False),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("subtitle", sa.String(400), nullable=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("link", sa.String(400), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_attention_events_rule_fired", "attention_events", ["rule_id", "fired_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_attention_events_rule_fired", table_name="attention_events")
    op.drop_table("attention_events")
    op.drop_column("attention_rules", "latched_at")
    op.drop_column("attention_rules", "window_started_at")
    op.drop_column("attention_rules", "period_days")
