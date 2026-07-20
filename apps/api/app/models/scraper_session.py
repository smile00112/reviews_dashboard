import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import SessionStatus


class ScraperSession(Base):
    __tablename__ = "scraper_sessions"
    # Exactly one row per provider: _get_or_create_session_record()'s
    # unordered .first() must always resolve to the same row, or a login can
    # be marked pending on one row and terminalized on another.
    __table_args__ = (UniqueConstraint("provider", name="uq_scraper_sessions_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="yandex")
    storage_state_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SessionStatus.missing,
    )
    # One-time confirmation code the operator submits via POST /session/code
    # while status == awaiting_code; consumed (cleared to None) the instant
    # the background login picks it up. Never returned by any API response.
    pending_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Why the last login/check ended as it did, and the step-by-step trace of
    # how it got there — the only diagnostics an operator gets, since the
    # Playwright run happens in a background task with no UI attached.
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
