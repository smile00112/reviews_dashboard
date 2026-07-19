from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ScrapeMode, ScrapeRunStatus


class ScrapeRequest(BaseModel):
    mode: ScrapeMode | None = None


class ScrapeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    mode: ScrapeMode
    status: ScrapeRunStatus
    started_at: datetime
    finished_at: datetime | None
    reviews_seen: int
    reviews_inserted: int
    reviews_updated: int
    # Feature 011: true = pagination provably exhausted; removal marking was allowed.
    full_pass: bool = False
    error_code: str | None
    error_message: str | None
    debug_screenshot_path: str | None
    debug_html_path: str | None


class ScrapeRunListResponse(BaseModel):
    items: list[ScrapeRunResponse]


class ScrapeStartResponse(BaseModel):
    scrape_run_id: UUID
    status: ScrapeRunStatus
    organization_count: int | None = None
