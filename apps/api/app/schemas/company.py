from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.organization import OrganizationResponse


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1)
    is_active: bool = True


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    branch_count: int = 0
    created_at: datetime
    updated_at: datetime


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]


class BranchCityGroup(BaseModel):
    city: str
    branches: list[OrganizationResponse]


class CompanyBranchesResponse(BaseModel):
    company_id: UUID
    groups: list[BranchCityGroup]
