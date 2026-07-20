from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SessionStatus


class SessionStatusResponse(BaseModel):
    status: SessionStatus
    last_login_at: datetime | None = None
    last_checked_at: datetime | None = None
    storage_state_path: str | None = None
    message: str | None = None


class LoginResponse(BaseModel):
    status: SessionStatus | str
    message: str


class CodeSubmission(BaseModel):
    # Yandex confirmation codes are short numeric strings; digits-only keeps
    # arbitrary text away from the Playwright fill() call downstream.
    code: str = Field(min_length=1, max_length=12, pattern=r"^\d+$")
