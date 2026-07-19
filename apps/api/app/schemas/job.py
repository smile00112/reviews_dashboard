from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import JobItemStatus, JobKind, JobRunStatus, JobTrigger, ReviewPlatform


class JobRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    trigger: JobTrigger
    triggered_by_user_id: UUID | None
    status: JobRunStatus
    started_at: datetime
    finished_at: datetime | None
    orgs_total: int
    orgs_succeeded: int
    orgs_skipped: int
    orgs_failed: int
    error_message: str | None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: JobKind
    platform: ReviewPlatform
    schedule_cron: str | None
    timezone: str
    is_enabled: bool
    options: dict
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_run: JobRunResponse | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]


class JobUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    schedule_cron: str | None = None
    options: dict | None = None

    @field_validator("options")
    @classmethod
    def _validate_force_full_every_days(cls, value: dict | None) -> dict | None:
        # Feature 011: interval must be a whole number of days >= 1 when present.
        if value is not None and "force_full_every_days" in value:
            days = value["force_full_every_days"]
            if not isinstance(days, int) or isinstance(days, bool) or days < 1:
                raise ValueError("force_full_every_days must be an integer >= 1")
        return value


class JobRunStartResponse(BaseModel):
    job_run_id: UUID
    status: JobRunStatus


class JobRunItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    status: JobItemStatus
    reason: str | None
    payload: dict
    scrape_run_id: UUID | None
    error_code: str | None
    error_message: str | None
    duration_ms: int | None


class JobRunListResponse(BaseModel):
    items: list[JobRunResponse]


class JobRunDetailResponse(JobRunResponse):
    job: JobResponse
    items: list[JobRunItemResponse] = Field(default_factory=list)
