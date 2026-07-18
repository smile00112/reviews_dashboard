"""background jobs: jobs, job_runs, job_run_items

Revision ID: 0014_background_jobs
Revises: 0013_review_idx_session_pend
Create Date: 2026-07-18

Additive. Определения фоновых задач + журнал их запусков. Существующая
``scrape_runs`` не меняется: связь идёт через job_run_items.scrape_run_id.
Сидит 4 задачи (metrics/reviews × yandex/gis2), все выключенными — расписание
включает оператор.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_background_jobs"
down_revision: Union[str, None] = "0013_review_idx_session_pend"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

platform_enum = postgresql.ENUM(
    "yandex", "google", "gis2", name="review_platform_enum", create_type=False
)
# create_type=False on all four: types are created/dropped explicitly below via
# .create()/.drop(); without this, op.create_table's column-embedded ENUM handling
# re-emits CREATE TYPE with checkfirst=False and collides with the explicit create.
job_kind_enum = postgresql.ENUM("org_metrics", "reviews", name="job_kind_enum", create_type=False)
job_trigger_enum = postgresql.ENUM("schedule", "manual", name="job_trigger_enum", create_type=False)
job_run_status_enum = postgresql.ENUM(
    "queued", "running", "success", "partial", "failed", "needs_manual_action", "cancelled",
    name="job_run_status_enum", create_type=False,
)
job_item_status_enum = postgresql.ENUM(
    "success", "skipped", "failed", "needs_manual_action", name="job_item_status_enum", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    job_kind_enum.create(bind, checkfirst=True)
    job_trigger_enum.create(bind, checkfirst=True)
    job_run_status_enum.create(bind, checkfirst=True)
    job_item_status_enum.create(bind, checkfirst=True)

    jobs = op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", job_kind_enum, nullable=False),
        sa.Column("platform", platform_enum, nullable=False),
        sa.Column("schedule_cron", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="Europe/Moscow"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("kind", "platform", name="uq_jobs_kind_platform"),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("trigger", job_trigger_enum, nullable=False),
        sa.Column(
            "triggered_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("status", job_run_status_enum, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orgs_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_index("ix_job_runs_job_started", "job_runs", ["job_id", sa.text("started_at DESC")])

    op.create_table(
        "job_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_run_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("status", job_item_status_enum, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "scrape_run_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_job_run_items_job_run_id", "job_run_items", ["job_run_id"])

    # Сиды: метрики в 04:00, отзывы в 05:00 — отзывам нужен свежий review_count.
    op.bulk_insert(
        jobs,
        [
            {
                "id": uuid.uuid4(), "kind": kind, "platform": platform,
                "schedule_cron": cron, "timezone": "Europe/Moscow",
                "is_enabled": False, "options": {"delay_seconds": 2},
            }
            for kind, cron in (("org_metrics", "0 4 * * *"), ("reviews", "0 5 * * *"))
            for platform in ("yandex", "gis2")
        ],
    )


def downgrade() -> None:
    op.drop_table("job_run_items")
    op.drop_table("job_runs")
    op.drop_table("jobs")
    bind = op.get_bind()
    job_item_status_enum.drop(bind, checkfirst=True)
    job_run_status_enum.drop(bind, checkfirst=True)
    job_trigger_enum.drop(bind, checkfirst=True)
    job_kind_enum.drop(bind, checkfirst=True)
