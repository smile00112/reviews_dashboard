"""Auth dependencies for the JSON API (feature 008 + configurable RBAC feature 016).

Reuses the feature-004 session cookie (signed with ADMIN_SECRET_KEY via the
already-mounted SessionMiddleware) and the ``users`` table. No JWT, no second
auth system (constitution Principle VII).

Authorization is permission-based: ``require_permission("action:...")`` guards a
route and returns 403 when the caller's role lacks the permission. The immutable
``admin`` role resolves to the full catalog (see PermissionService).
"""

import uuid
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import ADMIN_SLUG
from app.models.user import User
from app.services.permission_service import PermissionService


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        uid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_permission(permission: str) -> Callable[..., User]:
    """Dependency factory: allow only callers whose role grants ``permission``.

    401 when unauthenticated, 403 when authenticated but not permitted.
    """

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if not PermissionService().has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dependency


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Backwards-compatible admin gate: only the immutable admin system role.

    Retained for the few call sites that are genuinely admin-only (e.g. user
    management surfaces). Action routes use the specific require_permission(...).
    """
    role = user.role_ref
    if role is None or not (role.is_system and role.slug == ADMIN_SLUG):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user
