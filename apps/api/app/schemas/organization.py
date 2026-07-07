from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrganizationScrapeStatus, ScrapeMode


class OrganizationCreate(BaseModel):
    yandex_url: str
    preferred_scrape_mode: ScrapeMode = ScrapeMode.public
    # Branch fields (feature 008, additive/optional)
    name: str | None = None
    city: str | None = None
    region: str | None = None
    address: str | None = None
    company_id: UUID | None = None


class OrganizationUpdate(BaseModel):
    preferred_scrape_mode: ScrapeMode | None = None
    name: str | None = None
    # Branch fields (feature 008, additive/optional)
    city: str | None = None
    region: str | None = None
    address: str | None = None
    company_id: UUID | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    yandex_url: str
    normalized_url: str
    external_id: str | None
    address: str | None
    rating: float | None
    review_count: int | None
    preferred_scrape_mode: ScrapeMode
    last_successful_scrape_at: datetime | None
    last_scrape_status: OrganizationScrapeStatus
    city: str | None = None
    region: str | None = None
    company_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
