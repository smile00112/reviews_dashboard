from datetime import date, datetime
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


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int
