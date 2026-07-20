from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import SessionLocal, get_db
from app.models.enums import SessionStatus
from app.schemas.scraper_session import CodeSubmission, CookieImport, LoginResponse, SessionStatusResponse
from app.services.scrape_service import ScrapeService

router = APIRouter(prefix="/api/scraper/yandex", tags=["scraper-session"])


def _run_login_background() -> None:
    db = SessionLocal()
    try:
        ScrapeService(db).login_operator()
    finally:
        db.close()


def _run_check_background() -> None:
    db = SessionLocal()
    try:
        ScrapeService(db).check_session()
    finally:
        db.close()


def _to_status_response(session) -> SessionStatusResponse:
    return SessionStatusResponse(
        status=session.status,
        last_login_at=session.last_login_at,
        last_checked_at=session.last_checked_at,
        storage_state_path=session.storage_state_path,
        message=session.last_message,
        progress=session.progress,
    )


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_202_ACCEPTED)
def yandex_login(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> LoginResponse:
    """Schedule the Playwright login in the background (feature 010): the 202 is
    truthful now — poll GET /session for the outcome."""
    service = ScrapeService(db)
    session = service.get_session_record()
    if session.status == SessionStatus.pending:
        return LoginResponse(status=SessionStatus.pending, message="Login already in progress")
    service.mark_session_pending()
    background_tasks.add_task(_run_login_background)
    return LoginResponse(status=SessionStatus.pending, message="Login scheduled")


@router.get("/session", response_model=SessionStatusResponse)
def get_session(db: Session = Depends(get_db)) -> SessionStatusResponse:
    return _to_status_response(ScrapeService(db).get_session_status())


@router.post("/session/check", response_model=SessionStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def check_session(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> SessionStatusResponse:
    """Schedule the session check in the background; poll GET /session for the result."""
    service = ScrapeService(db)
    session = service.get_session_record()
    if session.status != SessionStatus.pending:
        session = service.mark_session_pending()
        background_tasks.add_task(_run_check_background)
    return _to_status_response(session)


@router.post("/session/import", response_model=SessionStatusResponse)
def import_session_cookies(
    payload: CookieImport,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> SessionStatusResponse:
    """Adopt a session from a browser the operator is already signed in to —
    the fallback when Passport's confirmation-code push cannot be delivered."""
    try:
        session = ScrapeService(db).import_session_cookies(payload.cookies)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return _to_status_response(session)


@router.post("/session/code", response_model=SessionStatusResponse)
def submit_session_code(
    payload: CodeSubmission,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> SessionStatusResponse:
    """Deliver the operator's confirmation code to a login that's paused in
    awaiting_code, waiting on ScrapeService._request_code's poll loop."""
    service = ScrapeService(db)
    session = service.get_session_record()
    if session.status != SessionStatus.awaiting_code:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending confirmation code request")
    session = service.submit_code(payload.code)
    return _to_status_response(session)
