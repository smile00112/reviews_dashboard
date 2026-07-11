import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import OrganizationScrapeStatus, ScrapeMode


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    yandex_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)  # Yandex оценка
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Yandex кол-во отзывов
    yandex_rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Yandex кол-во оценок
    # 2GIS platform metrics (operator-editable; no scraper). "gis2" prefix keeps identifiers valid.
    gis2_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    gis2_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    gis2_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gis2_rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Google Maps platform metrics (operator-editable; no scraper).
    google_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    google_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    google_rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_scrape_mode: Mapped[ScrapeMode] = mapped_column(
        Enum(ScrapeMode, name="scrape_mode_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ScrapeMode.public,
    )
    # Per-platform scrape status/timestamp (Yandex vs 2GIS scraped independently).
    _status_enum = Enum(
        OrganizationScrapeStatus,
        name="org_scrape_status_enum",
        values_callable=lambda x: [e.value for e in x],
    )
    yandex_scrape_status: Mapped[OrganizationScrapeStatus] = mapped_column(
        _status_enum, nullable=False, default=OrganizationScrapeStatus.pending
    )
    gis2_scrape_status: Mapped[OrganizationScrapeStatus] = mapped_column(
        _status_enum, nullable=False, default=OrganizationScrapeStatus.pending
    )
    yandex_last_successful_scrape_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    gis2_last_successful_scrape_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Admin panel columns (feature 004, additive)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_franchise: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Company parent (feature 008, additive). NULL = unassigned branch.
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    reviews = relationship("Review", back_populates="organization", cascade="all, delete-orphan")
    scrape_runs = relationship("ScrapeRun", back_populates="organization", cascade="all, delete-orphan")
    company = relationship("Company", back_populates="branches")

    def __str__(self) -> str:
        return self.name or str(self.id)
