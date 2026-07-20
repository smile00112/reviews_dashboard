from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SessionStatus


class SessionStatusResponse(BaseModel):
    status: SessionStatus
    last_login_at: datetime | None = None
    last_checked_at: datetime | None = None
    storage_state_path: str | None = None
    message: str | None = None
    # Step-by-step trace of the last login, surfaced to the operator's browser
    # console — the Playwright run has no other visible output.
    progress: list[dict] | None = None


class LoginResponse(BaseModel):
    status: SessionStatus | str
    message: str


class CookieImport(BaseModel):
    # Free-form on purpose: a storage state, a Cookie-Editor export, or a raw
    # Cookie header. Shape validation lives in scraper.cookie_import, which
    # can explain what is wrong; a regex here could only say "invalid".
    cookies: str = Field(min_length=1, max_length=200_000)


class CodeSubmission(BaseModel):
    # Yandex confirmation codes are short numeric strings; digits-only keeps
    # arbitrary text away from the Playwright fill() call downstream.
    code: str = Field(min_length=1, max_length=12, pattern=r"^\d+$")
