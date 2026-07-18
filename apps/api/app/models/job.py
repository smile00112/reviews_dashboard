import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, JSON, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobKind, ReviewPlatform


class Job(Base):
    """Определение фоновой задачи. Ровно одна строка на (kind, platform)."""

    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("kind", "platform", name="uq_jobs_kind_platform"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[JobKind] = mapped_column(
        Enum(JobKind, name="job_kind_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    platform: Mapped[ReviewPlatform] = mapped_column(
        Enum(ReviewPlatform, name="review_platform_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/Moscow")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    runs = relationship("JobRun", back_populates="job", cascade="all, delete-orphan")
