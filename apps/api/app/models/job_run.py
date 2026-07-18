import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobRunStatus, JobTrigger


class JobRun(Base):
    """Один запуск задачи — по расписанию или вручную."""

    __tablename__ = "job_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[JobTrigger] = mapped_column(
        Enum(JobTrigger, name="job_trigger_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[JobRunStatus] = mapped_column(
        Enum(JobRunStatus, name="job_run_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=JobRunStatus.queued,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orgs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("Job", back_populates="runs")
    items = relationship(
        "JobRunItem", back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
