from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.schemas.company import (
    BranchCityGroup,
    CompanyBranchesResponse,
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)
from app.schemas.organization import OrganizationResponse
from app.services.company_service import CompanyService

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _to_response(service: CompanyService, company) -> CompanyResponse:
    resp = CompanyResponse.model_validate(company)
    resp.branch_count = service.branch_count(company.id)
    return resp


@router.get("", response_model=CompanyListResponse)
def list_companies(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> CompanyListResponse:
    service = CompanyService(db)
    counts = service.branch_counts()  # one grouped query, not one COUNT per company
    items = []
    for company in service.list_all():
        resp = CompanyResponse.model_validate(company)
        resp.branch_count = counts.get(company.id, 0)
        items.append(resp)
    return CompanyListResponse(items=items)


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> CompanyResponse:
    service = CompanyService(db)
    return _to_response(service, service.create(payload))


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> CompanyResponse:
    service = CompanyService(db)
    company = service.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return _to_response(service, company)


@router.patch("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> CompanyResponse:
    service = CompanyService(db)
    company = service.update(company_id, payload)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return _to_response(service, company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> None:
    if not CompanyService(db).delete(company_id):
        raise HTTPException(status_code=404, detail="Company not found")


@router.get("/{company_id}/branches", response_model=CompanyBranchesResponse)
def company_branches(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> CompanyBranchesResponse:
    service = CompanyService(db)
    if not service.get(company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    groups = [
        BranchCityGroup(
            city=city,
            branches=[OrganizationResponse.model_validate(b) for b in members],
        )
        for city, members in service.list_branches_grouped_by_city(company_id)
    ]
    return CompanyBranchesResponse(company_id=company_id, groups=groups)
