import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# JSONB on PostgreSQL, generic JSON elsewhere (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")

from app.core.database import Base
from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "content_hash", name="uq_review_org_hash"),
        # Feature 010: list ordering + dashboard period/platform filters.
        Index("ix_reviews_org_review_date", "organization_id", "review_date"),
        Index("ix_reviews_org_first_seen", "organization_id", "first_seen_at"),
        Index("ix_reviews_org_platform", "organization_id", "platform"),
        # Feature 012: overview SQL aggregates.
        Index(
            "ix_reviews_org_unanswered",
            "organization_id",
            postgresql_where=text("response_text IS NULL"),
            sqlite_where=text("response_text IS NULL"),
        ),
        Index("ix_reviews_org_platform_first_seen", "organization_id", "platform", "first_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, default="yandex_maps")
    scrape_mode: Mapped[ScrapeMode] = mapped_column(
        Enum(ScrapeMode, name="review_scrape_mode_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    external_review_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    review_date_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Observation-time proxy: set once when response_text first goes absent->present, immutable
    # thereafter, NULL while a review has no stored response. Never feeds content_hash (feature 007).
    response_first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Real publication day of the business reply on the platform (MSK), parsed from the
    # source (Yandex businessComment.updatedTime / 2GIS official_answer date). NULL when
    # no reply or the date is unparseable. Synced with response_text on re-scrape; never
    # feeds content_hash. Distinct from response_first_seen_at (our observation time).
    response_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Feature 011: NULL = currently present on the platform. Set only after a full
    # scrape pass no longer sees the review; cleared on any re-sighting. Never
    # feeds content_hash.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin triage fields (feature 004, additive). Never feed content_hash.
    status: Mapped[ReviewStatus | None] = mapped_column(
        Enum(ReviewStatus, name="review_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        default=ReviewStatus.new,
    )
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    platform: Mapped[ReviewPlatform | None] = mapped_column(
        Enum(ReviewPlatform, name="review_platform_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        default=ReviewPlatform.yandex,
    )
    paid_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_marked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Derived analytics (feature 002). Additive, nullable; never feed content_hash.
    sentiment: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_sentiment_mismatch: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    problems: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="reviews")

    def __str__(self) -> str:
        return f"{self.author_name or 'Unknown'} ({self.rating}★)"
