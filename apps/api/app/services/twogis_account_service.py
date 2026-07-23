"""2GIS business-cabinet session service (feature 017).

Manages the ``provider="2gis"`` row in ``scraper_sessions`` — the same table and
``SessionStatus`` enum the Yandex operator session uses. Scope is import + check only:
no automated login, no ``pending``/``awaiting_code`` background flow, so every method here
is synchronous (the check is one fast HTTP call).

The credential is a Bearer access token (see ``scraper/twogis_account.py``), not cookies.
The stored session is not consumed by any scraper or job yet; this exists so an operator
can save a cabinet token and verify it works, by analogy with the Yandex session.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import SessionStatus
from app.models.scraper_session import ScraperSession
from app.scraper.twogis_account import TwogisAccountScraper, extract_bearer_token

PROVIDER = "2gis"


class TwogisAccountService:
    def __init__(self, db: Session, scraper: TwogisAccountScraper | None = None) -> None:
        self.db = db
        self.scraper = scraper or TwogisAccountScraper()

    def _get_or_create_session_record(self) -> ScraperSession:
        session = self.db.query(ScraperSession).filter(ScraperSession.provider == PROVIDER).first()
        if not session:
            session = ScraperSession(
                provider=PROVIDER,
                storage_state_path=settings.twogis_storage_state_path,
                status=SessionStatus.missing,
            )
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
        return session

    def get_session_record(self) -> ScraperSession:
        return self._get_or_create_session_record()

    def get_session_status(self) -> ScraperSession:
        """Current row, with the same file-heuristic refresh the Yandex session uses:
        a ``valid`` verdict whose state file vanished falls back to ``missing``; a bare
        state file that appeared without this app writing it bootstraps to ``valid``.
        Verdicts from a real check (``expired``/``needs_manual_action``) are left alone."""
        session = self._get_or_create_session_record()
        path = Path(session.storage_state_path)
        has_state = path.exists() and path.stat().st_size > 0
        if session.status == SessionStatus.valid and not has_state:
            session.status = SessionStatus.missing
        elif session.status == SessionStatus.missing and has_state:
            session.status = SessionStatus.valid
        self.db.commit()
        return session

    def import_session_cookies(self, text: str) -> ScraperSession:
        """Adopt the Bearer access token pasted from the 2GIS cabinet.

        Accepts a full request-headers block, an ``Authorization: Bearer …`` line, or the
        bare token — whatever is pasted, the token is extracted. Raises ValueError (→ 422)
        when no token is found, before touching the filesystem, so a rejected paste leaves
        no half-written state behind. The method name is kept for symmetry with the Yandex
        session API; the payload is a token, not cookies.
        """
        token = extract_bearer_token(text)
        if not token:
            raise ValueError(
                "No 2GIS access token found. Copy the Authorization: Bearer value from a "
                "DevTools request to api.account.2gis.com (Network tab → Request Headers)."
            )
        session = self._get_or_create_session_record()

        path = Path(session.storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"access_token": token}, ensure_ascii=False), encoding="utf-8")

        now = datetime.now(timezone.utc)
        # Imported, not yet verified: mark valid optimistically (mirrors the Yandex import)
        # — the operator confirms with "Проверить", which flips it to expired on a 401.
        session.status = SessionStatus.valid
        session.last_login_at = now
        session.last_checked_at = now
        session.last_message = "Token imported — press Проверить to verify"
        session.progress = None
        self.db.commit()
        return session

    def check_session(self) -> ScraperSession:
        """Verify the saved session against the live cabinet API and persist the verdict."""
        session = self._get_or_create_session_record()
        status, message = self.scraper.check_session(session.storage_state_path)
        session.status = status
        session.last_message = message
        session.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return session
