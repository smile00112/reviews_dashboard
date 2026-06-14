from datetime import datetime

from pydantic import BaseModel

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
