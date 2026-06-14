import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ScrapeMode, ScrapeRunStatus


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    mode: Mapped[ScrapeMode] = mapped_column(
        Enum(ScrapeMode, name="run_scrape_mode_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[ScrapeRunStatus] = mapped_column(
        Enum(ScrapeRunStatus, name="scrape_run_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ScrapeRunStatus.queued,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviews_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviews_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviews_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    debug_screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    debug_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization = relationship("Organization", back_populates="scrape_runs")
