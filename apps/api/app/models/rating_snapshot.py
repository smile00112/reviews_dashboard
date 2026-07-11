import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ReviewPlatform


class RatingSnapshot(Base):
    """Daily point-in-time capture of an organization's rating per platform.

    Enables period-over-period rating deltas on the network overview (feature 009).
    Additive; never participates in review deduplication. One row per
    (organization, platform, day) — same-day capture upserts.
    """

    __tablename__ = "rating_snapshot"
    __table_args__ = (
        UniqueConstraint("organization_id", "platform", "captured_on", name="uq_rating_snapshot_org_platform_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[ReviewPlatform] = mapped_column(
        Enum(ReviewPlatform, name="review_platform_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization = relationship("Organization")

    def __str__(self) -> str:
        return f"{self.organization_id} {self.platform} {self.captured_on}: {self.rating}"
