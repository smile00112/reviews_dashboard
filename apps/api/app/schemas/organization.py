from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrganizationScrapeStatus, ScrapeMode


class PlatformMetricsMixin(BaseModel):
    """Operator-editable multi-platform metrics (no scraper for 2GIS/Google)."""

    yandex_rating_count: int | None = None
    gis2_url: str | None = None
    gis2_rating: float | None = None
    gis2_review_count: int | None = None
    gis2_rating_count: int | None = None
    google_url: str | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_rating_count: int | None = None


class OrganizationCreate(PlatformMetricsMixin):
    yandex_url: str
    preferred_scrape_mode: ScrapeMode = ScrapeMode.public
    # Branch fields (feature 008, additive/optional)
    name: str | None = None
    city: str | None = None
    region: str | None = None
    address: str | None = None
    company_id: UUID | None = None


class OrganizationUpdate(PlatformMetricsMixin):
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
    # Nullable in the ORM/DB: 2GIS-only orgs have no Yandex presence.
    yandex_url: str | None
    normalized_url: str | None
    external_id: str | None
    address: str | None
    rating: float | None
    review_count: int | None
    yandex_rating_count: int | None = None
    gis2_url: str | None = None
    gis2_rating: float | None = None
    gis2_review_count: int | None = None
    gis2_rating_count: int | None = None
    google_url: str | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_rating_count: int | None = None
    preferred_scrape_mode: ScrapeMode
    yandex_scrape_status: OrganizationScrapeStatus
    gis2_scrape_status: OrganizationScrapeStatus
    yandex_last_successful_scrape_at: datetime | None = None
    gis2_last_successful_scrape_at: datetime | None = None
    city: str | None = None
    region: str | None = None
    company_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    total: int = 0
