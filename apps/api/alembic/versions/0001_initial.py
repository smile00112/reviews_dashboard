"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    scrape_mode_enum = postgresql.ENUM(
        "public", "operator_auth", name="scrape_mode_enum", create_type=False
    )
    org_status_enum = postgresql.ENUM(
        "pending", "running", "success", "failed", "needs_manual_action",
        name="org_scrape_status_enum", create_type=False
    )
    run_status_enum = postgresql.ENUM(
        "queued", "running", "success", "failed", "needs_manual_action",
        name="scrape_run_status_enum", create_type=False
    )
    session_status_enum = postgresql.ENUM(
        "missing", "valid", "expired", "needs_manual_action",
        name="session_status_enum", create_type=False
    )
    scrape_mode_enum.create(op.get_bind(), checkfirst=True)
    org_status_enum.create(op.get_bind(), checkfirst=True)
    run_status_enum.create(op.get_bind(), checkfirst=True)
    session_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("yandex_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("preferred_scrape_mode", scrape_mode_enum, nullable=False),
        sa.Column("last_successful_scrape_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scrape_status", org_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("scrape_mode", scrape_mode_enum, nullable=False),
        sa.Column("external_review_id", sa.Text(), nullable=True),
        sa.Column("author_name", sa.Text(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=False),
        sa.Column("review_date_text", sa.Text(), nullable=True),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "content_hash", name="uq_review_org_hash"),
    )
    op.create_index("ix_reviews_organization_id", "reviews", ["organization_id"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("mode", scrape_mode_enum, nullable=False),
        sa.Column("status", run_status_enum, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviews_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviews_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviews_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("debug_screenshot_path", sa.Text(), nullable=True),
        sa.Column("debug_html_path", sa.Text(), nullable=True),
    )
    op.create_index("ix_scrape_runs_organization_id", "scrape_runs", ["organization_id"])

    op.create_table(
        "scraper_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("storage_state_path", sa.Text(), nullable=False),
        sa.Column("status", session_status_enum, nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scraper_sessions")
    op.drop_table("scrape_runs")
    op.drop_table("reviews")
    op.drop_table("organizations")
    op.execute("DROP TYPE IF EXISTS session_status_enum")
    op.execute("DROP TYPE IF EXISTS scrape_run_status_enum")
    op.execute("DROP TYPE IF EXISTS org_scrape_status_enum")
    op.execute("DROP TYPE IF EXISTS scrape_mode_enum")
