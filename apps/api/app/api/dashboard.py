"""Network overview dashboard endpoint (feature 009). Read-only, authenticated."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardOverview
from app.services.dashboard_service import PERIOD_DAYS, DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_PLATFORMS = {"all", "yandex", "google", "gis2"}


@router.get("/overview", response_model=DashboardOverview)
def get_overview(
    period: str = Query(default="30d"),
    platform: str = Query(default="all"),
    org_ids: list[UUID] | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardOverview:
    if period not in PERIOD_DAYS:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"Invalid period: {period}")
    if platform not in _PLATFORMS:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"Invalid platform: {platform}")

    data = DashboardService(db).overview(
        period=period, platform=platform, org_ids=org_ids, company_id=company_id
    )
    return DashboardOverview.model_validate(data)
