import uuid

from sqlalchemy import Enum, ForeignKey, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobItemStatus


class JobRunItem(Base):
    """Результат обработки одной организации внутри запуска.

    ``payload`` хранит «было → стало» в форме, зависящей от типа задачи:
      * org_metrics: rating_before/after, review_count_before/after, rating_count_before/after
      * reviews:     platform_total, scraped_before, reviews_seen, inserted, updated
    """

    __tablename__ = "job_run_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[JobItemStatus] = mapped_column(
        Enum(JobItemStatus, name="job_item_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    scrape_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run = relationship("JobRun", back_populates="items")
    organization = relationship("Organization")
