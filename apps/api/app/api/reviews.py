from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import ReviewPlatform
from app.schemas.review import ReviewListResponse, ReviewResponse, ReviewSummaryResponse
from app.services.organization_service import OrganizationService
from app.services.review_service import ReviewService

router = APIRouter(tags=["reviews"])


def _to_review_response(review, organization_name: str | None = None) -> ReviewResponse:
    data = ReviewResponse.model_validate(review)
    data.organization_name = organization_name
    return data


@router.get("/api/reviews", response_model=ReviewListResponse)
def list_reviews(
    organization_id: UUID | None = None,
    rating: int | None = Query(default=None, ge=1, le=5),
    date_from: date | None = None,
    date_to: date | None = None,
    new_only: bool = False,
    status: str | None = Query(default=None, pattern="^(all|unanswered|in_progress|escalated|answered)$"),
    platform: ReviewPlatform | None = None,
    tone: str | None = Query(default=None, pattern="^(neg|pos)$"),
    period: str | None = Query(default=None, pattern="^(24h|7d|30d|year)$"),
    is_paid: bool | None = None,
    aspect: str | None = None,
    sort: str = Query(default="new", pattern="^(new|criticality)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewListResponse:
    rows, total = ReviewService(db).list_global(
        organization_id=organization_id,
        limit=limit,
        offset=offset,
        rating=rating,
        date_from=date_from,
        date_to=date_to,
        new_only=new_only,
        status_tab=None if status in (None, "all") else status,
        platform=platform,
        tone=tone,
        period=period,
        is_paid=is_paid,
        aspect=aspect,
        sort=sort,
    )
    items = [_to_review_response(review, org_name) for review, org_name in rows]
    return ReviewListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/api/organizations/{organization_id}/reviews", response_model=ReviewListResponse)
def list_organization_reviews(
    organization_id: UUID,
    rating: int | None = Query(default=None, ge=1, le=5),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewListResponse:
    if not OrganizationService(db).get(organization_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    items, total = ReviewService(db).list_for_organization(
        organization_id,
        limit=limit,
        offset=offset,
        rating=rating,
        date_from=date_from,
        date_to=date_to,
    )
    org = OrganizationService(db).get(organization_id)
    org_name = org.name if org else None
    return ReviewListResponse(
        items=[_to_review_response(item, org_name) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/reviews/summary", response_model=ReviewSummaryResponse)
def reviews_summary(
    organization_id: UUID | None = None,
    rating: int | None = Query(default=None, ge=1, le=5),
    date_from: date | None = None,
    date_to: date | None = None,
    platform: ReviewPlatform | None = None,
    tone: str | None = Query(default=None, pattern="^(neg|pos)$"),
    period: str | None = Query(default=None, pattern="^(24h|7d|30d|year)$"),
    is_paid: bool | None = None,
    aspect: str | None = None,
    db: Session = Depends(get_db),
) -> ReviewSummaryResponse:
    data = ReviewService(db).summary(
        organization_id=organization_id,
        rating=rating,
        date_from=date_from,
        date_to=date_to,
        platform=platform,
        tone=tone,
        period=period,
        is_paid=is_paid,
        aspect=aspect,
    )
    return ReviewSummaryResponse(**data)
