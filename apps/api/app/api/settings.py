from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services.settings_service import SLA_KEY, SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _current(svc: SettingsService) -> SettingsResponse:
    return SettingsResponse(overview_sla_threshold_minutes=svc.sla_threshold_minutes())


@router.get("", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> SettingsResponse:
    return _current(SettingsService(db))


@router.patch("", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> SettingsResponse:
    svc = SettingsService(db)
    svc.set(SLA_KEY, payload.overview_sla_threshold_minutes)
    return _current(svc)
