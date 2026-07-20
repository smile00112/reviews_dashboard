"""Network overview dashboard endpoint (feature 009). Read-only, authenticated."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardOverview, DashboardRatings
from app.services.dashboard_service import CUSTOM_PERIOD, PERIOD_DAYS, DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_PLATFORMS = {"all", "yandex", "google", "gis2"}


@router.get("/overview", response_model=DashboardOverview)
def get_overview(
    period: str = Query(default="30d"),
    platform: str = Query(default="all"),
    org_ids: list[UUID] | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardOverview:
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=422, detail=f"Invalid period: {period}")
    if platform not in _PLATFORMS:
        raise HTTPException(status_code=422, detail=f"Invalid platform: {platform}")
    # Feature 013: a custom range needs both inclusive bounds; dates sent with a
    # preset period are ignored rather than silently reshaping the window.
    if period == CUSTOM_PERIOD:
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=422, detail="period=custom requires both date_from and date_to"
            )
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must not be after date_to")

    data = DashboardService(db).overview(
        period=period,
        platform=platform,
        org_ids=org_ids,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
    )
    return DashboardOverview.model_validate(data)


def _validate_filters(period: str, platform: str, date_from: date | None, date_to: date | None) -> None:
    """Shared query validation for the dashboard endpoints (features 013, 014)."""
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=422, detail=f"Invalid period: {period}")
    if platform not in _PLATFORMS:
        raise HTTPException(status_code=422, detail=f"Invalid platform: {platform}")
    if period == CUSTOM_PERIOD:
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=422, detail="period=custom requires both date_from and date_to"
            )
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must not be after date_to")


@router.get("/ratings", response_model=DashboardRatings)
def get_ratings(
    period: str = Query(default="30d"),
    platform: str = Query(default="all"),
    org_ids: list[UUID] | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardRatings:
    """Comparative rating analytics for the ratings page (feature 014).

    Same filter contract as ``/overview`` — the web page reuses one filter
    component for both.
    """
    _validate_filters(period, platform, date_from, date_to)

    data = DashboardService(db).ratings(
        period=period,
        platform=platform,
        org_ids=org_ids,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
    )
    return DashboardRatings.model_validate(data)
