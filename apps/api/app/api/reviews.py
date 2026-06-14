from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.review import ReviewListResponse, ReviewResponse
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
