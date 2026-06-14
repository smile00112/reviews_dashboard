from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import SessionStatus
from app.schemas.scraper_session import LoginResponse, SessionStatusResponse
from app.services.scrape_service import ScrapeService

router = APIRouter(prefix="/api/scraper/yandex", tags=["scraper-session"])


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_202_ACCEPTED)
def yandex_login(db: Session = Depends(get_db)) -> LoginResponse:
    session_status, message = ScrapeService(db).login_operator()
    return LoginResponse(status=session_status, message=message)


@router.get("/session", response_model=SessionStatusResponse)
def get_session(db: Session = Depends(get_db)) -> SessionStatusResponse:
    session = ScrapeService(db).get_session_status()
    return SessionStatusResponse(
        status=session.status,
        last_login_at=session.last_login_at,
        last_checked_at=session.last_checked_at,
        storage_state_path=session.storage_state_path,
    )


@router.post("/session/check", response_model=SessionStatusResponse)
def check_session(db: Session = Depends(get_db)) -> SessionStatusResponse:
    session = ScrapeService(db).check_session()
    return SessionStatusResponse(
        status=session.status,
        last_login_at=session.last_login_at,
        last_checked_at=session.last_checked_at,
        storage_state_path=session.storage_state_path,
    )
