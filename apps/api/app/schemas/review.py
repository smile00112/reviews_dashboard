from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ScrapeMode


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
