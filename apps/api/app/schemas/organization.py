from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrganizationScrapeStatus, ScrapeMode


class OrganizationCreate(BaseModel):
    yandex_url: str
    preferred_scrape_mode: ScrapeMode = ScrapeMode.public


class OrganizationUpdate(BaseModel):
    preferred_scrape_mode: ScrapeMode | None = None
    name: str | None = None
    twogis_url: str | None = None
    google_url: str | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    yandex_url: str
    normalized_url: str
    twogis_url: str | None
    google_url: str | None
    external_id: str | None
    address: str | None
    rating: float | None
    review_count: int | None
    preferred_scrape_mode: ScrapeMode
    last_successful_scrape_at: datetime | None
    last_scrape_status: OrganizationScrapeStatus
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
