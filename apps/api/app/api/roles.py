"""Roles & permissions management API (feature 016).

All endpoints require the ``action:roles.manage`` permission (admin, or any role
granted it). The immutable admin system role cannot be modified or deleted.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import catalog
from app.models.role import Role
from app.schemas.role import (
    GrantUpdate,
    PermissionCatalog,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)
from app.services.role_service import RoleError, RoleService

router = APIRouter(prefix="/api/roles", tags=["roles"])

# Every route in this router is guarded by the roles-management permission.
_guard = Depends(require_permission("action:roles.manage"))


def _to_response(service: RoleService, role: Role, counts: dict | None = None) -> RoleResponse:
    count = counts.get(role.id, 0) if counts is not None else service.user_count(role.id)
    return RoleResponse(
        id=role.id,
        slug=role.slug,
        name=role.name,
        is_system=role.is_system,
        description=role.description,
        permissions=service.permissions_for(role),
        user_count=count,
    )


def _raise(err: RoleError) -> None:
    raise HTTPException(status_code=err.status_code, detail=str(err))


@router.get("/catalog", response_model=PermissionCatalog)
def get_catalog(_perm=_guard) -> PermissionCatalog:
    return PermissionCatalog(**catalog())


@router.get("", response_model=list[RoleResponse])
def list_roles(db: Session = Depends(get_db), _perm=_guard) -> list[RoleResponse]:
    service = RoleService(db)
    counts = service.user_counts()
    return [_to_response(service, r, counts) for r in service.list_roles()]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: Session = Depends(get_db), _perm=_guard) -> RoleResponse:
    service = RoleService(db)
    try:
        role = service.create(payload.name, payload.description, payload.permissions)
    except RoleError as err:
        _raise(err)
    return _to_response(service, role)


@router.patch("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: UUID, payload: RoleUpdate, db: Session = Depends(get_db), _perm=_guard
) -> RoleResponse:
    service = RoleService(db)
    try:
        role = service.update(role_id, payload.name, payload.description)
    except RoleError as err:
        _raise(err)
    return _to_response(service, role)


@router.put("/{role_id}/permissions", response_model=RoleResponse)
def set_permissions(
    role_id: UUID, payload: GrantUpdate, db: Session = Depends(get_db), _perm=_guard
) -> RoleResponse:
    service = RoleService(db)
    try:
        role = service.set_permissions(role_id, payload.permissions)
    except RoleError as err:
        _raise(err)
    return _to_response(service, role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: UUID, db: Session = Depends(get_db), _perm=_guard) -> None:
    service = RoleService(db)
    try:
        service.delete(role_id)
    except RoleError as err:
        _raise(err)
