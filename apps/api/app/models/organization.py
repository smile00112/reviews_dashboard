import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import OrganizationScrapeStatus, ScrapeMode


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    yandex_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Additional map-provider links for the same point (feature 008, additive).
    # Display/reference only; never feed the scrape URL or the dedup hash.
    twogis_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_scrape_mode: Mapped[ScrapeMode] = mapped_column(
        Enum(ScrapeMode, name="scrape_mode_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ScrapeMode.public,
    )
    last_successful_scrape_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scrape_status: Mapped[OrganizationScrapeStatus] = mapped_column(
        Enum(OrganizationScrapeStatus, name="org_scrape_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrganizationScrapeStatus.pending,
    )
    # Admin panel columns (feature 004, additive)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_franchise: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    reviews = relationship("Review", back_populates="organization", cascade="all, delete-orphan")
    scrape_runs = relationship("ScrapeRun", back_populates="organization", cascade="all, delete-orphan")

    def __str__(self) -> str:
        return self.name or str(self.id)
