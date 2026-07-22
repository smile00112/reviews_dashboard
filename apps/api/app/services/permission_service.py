"""Effective-permission resolution for the RBAC system (feature 016).

The immutable ``admin`` system role resolves to the entire catalog without any
grant rows stored for it, so it can never be partially configured or downgraded
(constitution v1.5.0, Principle VII). Every other role's effective set is exactly
its stored grants; absence of a grant means denied.
"""

from __future__ import annotations

from app.core.permissions import ADMIN_SLUG, ALL_PERMISSIONS
from app.models.user import User


class PermissionService:
    def __init__(self, db=None):
        # db kept for signature symmetry with sibling services; resolution reads
        # the already-loaded role relationship, so no query is needed here.
        self.db = db

    @staticmethod
    def _is_admin(user: User) -> bool:
        role = user.role_ref
        return bool(role is not None and role.is_system and role.slug == ADMIN_SLUG)

    def effective_permissions(self, user: User) -> set[str]:
        if self._is_admin(user):
            return set(ALL_PERMISSIONS.keys())
        role = user.role_ref
        if role is None:
            return set()
        return set(role.permission_keys)

    def has_permission(self, user: User, permission: str) -> bool:
        if self._is_admin(user):
            return True
        return permission in self.effective_permissions(user)
