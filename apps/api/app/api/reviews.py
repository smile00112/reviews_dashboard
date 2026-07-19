from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.enums import ReviewPlatform
from app.models.user import User
from app.schemas.review import (
    AspectsResponse,
    ReviewListResponse,
    ReviewPatchRequest,
    ReviewResponse,
    ReviewSummaryResponse,
)
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
    removed: str = Query(default="active", pattern="^(active|removed|all)$"),
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
        removed=removed,
    )
    items = [_to_review_response(review, org_name) for review, org_name in rows]
    return ReviewListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/api/organizations/{organization_id}/reviews", response_model=ReviewListResponse)
def list_organization_reviews(
    organization_id: UUID,
    rating: int | None = Query(default=None, ge=1, le=5),
    date_from: date | None = None,
    date_to: date | None = None,
    removed: str = Query(default="active", pattern="^(active|removed|all)$"),
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
        removed=removed,
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


@router.get("/api/reviews/aspects", response_model=AspectsResponse)
def reviews_aspects(
    period: str = Query(default="30d", pattern="^(24h|7d|30d|year)$"),
    organization_id: UUID | None = None,
    platform: ReviewPlatform | None = None,
    aspect: str | None = None,
    db: Session = Depends(get_db),
) -> AspectsResponse:
    data = ReviewService(db).aspects(
        period=period, organization_id=organization_id, platform=platform, aspect=aspect
    )
    return AspectsResponse(**data)


@router.patch("/api/reviews/{review_id}", response_model=ReviewResponse)
def patch_review(
    review_id: UUID,
    payload: ReviewPatchRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ReviewResponse:
    review = ReviewService(db).update_triage(review_id, payload.model_dump(exclude_unset=True))
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    org = OrganizationService(db).get(review.organization_id)
    return _to_review_response(review, org.name if org else None)
