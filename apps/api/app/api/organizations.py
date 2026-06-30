from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analytics import AnalyzeResult, OrganizationAnalyticsSummary
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.analysis_service import AnalysisService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("", response_model=OrganizationListResponse)
def list_organizations(db: Session = Depends(get_db)) -> OrganizationListResponse:
    items = OrganizationService(db).list_all()
    return OrganizationListResponse(items=items)


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)) -> OrganizationResponse:
    service = OrganizationService(db)
    try:
        org = service.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return org


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(organization_id: UUID, db: Session = Depends(get_db)) -> OrganizationResponse:
    org = OrganizationService(db).get(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    org = OrganizationService(db).update(organization_id, payload)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(organization_id: UUID, db: Session = Depends(get_db)) -> None:
    deleted = OrganizationService(db).delete(organization_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Organization not found")


@router.post("/{organization_id}/analyze", response_model=AnalyzeResult)
def analyze_organization(organization_id: UUID, db: Session = Depends(get_db)) -> AnalyzeResult:
    """Run (or re-run) deterministic local analytics over the org's stored reviews.

    Idempotent; does not re-scrape and never changes any review's content_hash.
    """
    result = AnalysisService(db).analyze_organization(organization_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return AnalyzeResult(**result)


@router.get("/{organization_id}/analytics", response_model=OrganizationAnalyticsSummary)
def organization_analytics(organization_id: UUID, db: Session = Depends(get_db)) -> OrganizationAnalyticsSummary:
    summary = AnalysisService(db).summary(organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationAnalyticsSummary(**summary)
