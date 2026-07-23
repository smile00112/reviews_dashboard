"""2GIS business-cabinet session endpoints (feature 017).

Import + check only, by analogy with the Yandex operator session — but synchronous, since
there is no Playwright login: the check is a single HTTP call to the cabinet API. All
mutating routes are guarded by the same permission as the Yandex session.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.schemas.scraper_session import CookieImport, SessionStatusResponse
from app.services.twogis_account_service import TwogisAccountService

router = APIRouter(prefix="/api/scraper/2gis", tags=["scraper-session-2gis"])


def _to_status_response(session) -> SessionStatusResponse:
    return SessionStatusResponse(
        status=session.status,
        last_login_at=session.last_login_at,
        last_checked_at=session.last_checked_at,
        storage_state_path=session.storage_state_path,
        message=session.last_message,
        progress=session.progress,
    )


@router.get("/session", response_model=SessionStatusResponse)
def get_session(db: Session = Depends(get_db)) -> SessionStatusResponse:
    return _to_status_response(TwogisAccountService(db).get_session_status())


@router.post("/session/import", response_model=SessionStatusResponse)
def import_session_cookies(
    payload: CookieImport,
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("action:scraper_session.manage")),
) -> SessionStatusResponse:
    """Adopt a 2GIS cabinet session from a browser the operator is already signed in to."""
    try:
        session = TwogisAccountService(db).import_session_cookies(payload.cookies)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return _to_status_response(session)


@router.post("/session/check", response_model=SessionStatusResponse)
def check_session(
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("action:scraper_session.manage")),
) -> SessionStatusResponse:
    """Verify the saved cabinet session against the live 2GIS cabinet API (synchronous)."""
    return _to_status_response(TwogisAccountService(db).check_session())
