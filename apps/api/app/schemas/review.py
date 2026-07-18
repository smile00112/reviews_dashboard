from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    source: str
    scrape_mode: ScrapeMode
    external_review_id: str | None
    author_name: str | None
    rating: int
    review_text: str
    review_date_text: str | None
    review_date: date | None
    response_text: str | None
    # Internal triage (feature 004): DB-only workflow, nothing is published anywhere.
    status: ReviewStatus | None = None
    is_paid: bool = False
    paid_cost: int | None = None
    platform: ReviewPlatform | None = None
    # Time we first observed a response on this review (feature 007); null when none seen.
    response_first_seen_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    # Derived analytics (feature 002); null when not yet analyzed.
    sentiment: str | None = None
    sentiment_score: float | None = None
    sentiment_confidence: float | None = None
    rating_sentiment_mismatch: bool | None = None
    problems: list[dict[str, Any]] | None = None
    analyzed_at: datetime | None = None


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int


class ReviewSummaryResponse(BaseModel):
    total: int
    new_count: int
    unanswered: int
    in_progress: int
    escalated: int
    answered: int
    overdue_24h: int
    negative: int


class AspectStat(BaseModel):
    category: str
    label: str
    mentions: int
    delta_pct: int | None
    pos: int
    neu: int
    neg: int


class AspectTrendPoint(BaseModel):
    date: date
    count: int


class AspectTrend(BaseModel):
    category: str
    days: int
    series: list[AspectTrendPoint]


class AspectsResponse(BaseModel):
    aspects: list[AspectStat]
    trend: AspectTrend | None = None


class ReviewPatchRequest(BaseModel):
    status: ReviewStatus | None = None
    is_paid: bool | None = None
    paid_cost: int | None = Field(default=None, ge=0)

    @field_validator("is_paid")
    @classmethod
    def _is_paid_not_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("is_paid cannot be null")
        return value
