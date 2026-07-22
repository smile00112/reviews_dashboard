"""Role lifecycle + seeding for the RBAC system (feature 016).

This module hosts the seed helper used by the seed-users script and tests. The
full admin-facing CRUD (create/rename/grants/delete with guards) is added in the
User Story 3 phase.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN_SLUG, DEFAULT_ROLES, LEGACY_ROLE_MAP, is_valid_permission
from app.models.role import Role, RolePermission
from app.models.user import User


class RoleError(Exception):
    """Base for role-management guard violations."""

    status_code = 400


class RoleNotFound(RoleError):
    status_code = 404


class RoleImmutable(RoleError):
    """Attempt to modify/delete the immutable admin system role."""

    status_code = 403


class RoleNameConflict(RoleError):
    status_code = 409


class RoleInUse(RoleError):
    status_code = 409


class UnknownPermission(RoleError):
    status_code = 422


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(name: str) -> str:
    out = "".join(_TRANSLIT.get(ch, ch) for ch in name.strip().lower())
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")
    return out or "role"


def get_role_by_slug(db: Session, slug: str) -> Role | None:
    return db.query(Role).filter(Role.slug == slug).first()


def seed_default_roles(db: Session) -> dict[str, Role]:
    """Idempotently create the three default roles with their grants.

    Returns a {slug: Role} map. Existing roles (matched by slug) are left as-is
    so an operator's later edits to call_center/manager grants are never clobbered.
    """
    result: dict[str, Role] = {}
    for spec in DEFAULT_ROLES:
        role = get_role_by_slug(db, spec["slug"])
        if role is None:
            role = Role(
                slug=spec["slug"],
                name=spec["name"],
                is_system=spec["is_system"],
                description=spec.get("description"),
            )
            db.add(role)
            db.flush()  # assign id before adding grants
            for perm in spec["grants"]:
                db.add(RolePermission(role_id=role.id, permission=perm))
        result[spec["slug"]] = role
    db.flush()
    return result


def map_legacy_role(legacy_value: str | None) -> str:
    """Map a legacy users.role enum value to the new role slug it becomes."""
    if legacy_value is None:
        return LEGACY_ROLE_MAP["review_operator"]
    return LEGACY_ROLE_MAP.get(legacy_value, LEGACY_ROLE_MAP["review_operator"])


class RoleService:
    """Admin-facing role CRUD + grant editing with the feature-016 guards."""

    def __init__(self, db: Session):
        self.db = db

    # --- reads ---------------------------------------------------------------

    def list_roles(self) -> list[Role]:
        return self.db.query(Role).order_by(Role.is_system.desc(), Role.name).all()

    def get(self, role_id: uuid.UUID) -> Role:
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if role is None:
            raise RoleNotFound("Role not found")
        return role

    def user_count(self, role_id: uuid.UUID) -> int:
        return self.db.query(User).filter(User.role_id == role_id).count()

    def user_counts(self) -> dict[uuid.UUID, int]:
        rows = (
            self.db.query(User.role_id, func.count(User.id))
            .group_by(User.role_id)
            .all()
        )
        return {rid: n for rid, n in rows}

    # --- validation helpers --------------------------------------------------

    def _validate_permissions(self, permissions: list[str]) -> list[str]:
        seen: list[str] = []
        for perm in permissions:
            if not is_valid_permission(perm):
                raise UnknownPermission(f"Unknown permission: {perm}")
            if perm not in seen:
                seen.append(perm)
        return seen

    def _ensure_name_free(self, name: str, exclude_id: uuid.UUID | None = None) -> None:
        # Case-insensitive compare in Python: SQLite's lower() doesn't fold
        # non-ASCII (Cyrillic) the way Python's str.lower() does, so a DB-side
        # func.lower() comparison would miss "Дубль" vs "дубль".
        target = name.strip().casefold()
        for rid, rname in self.db.query(Role.id, Role.name).all():
            if rid != exclude_id and rname.casefold() == target:
                raise RoleNameConflict("A role with this name already exists")

    def _unique_slug(self, base: str) -> str:
        slug = base
        n = 2
        while self.db.query(Role).filter(Role.slug == slug).first() is not None:
            slug = f"{base}_{n}"
            n += 1
        return slug

    # --- writes --------------------------------------------------------------

    def create(self, name: str, description: str | None, permissions: list[str]) -> Role:
        name = name.strip()
        if not name:
            raise UnknownPermission("name must not be blank")  # 422-ish; schema catches first
        self._ensure_name_free(name)
        grants = self._validate_permissions(permissions)
        role = Role(
            name=name,
            slug=self._unique_slug(slugify(name)),
            is_system=False,
            description=description,
        )
        self.db.add(role)
        self.db.flush()
        for perm in grants:
            self.db.add(RolePermission(role_id=role.id, permission=perm))
        self.db.commit()
        self.db.refresh(role)
        return role

    def update(self, role_id: uuid.UUID, name: str | None, description: str | None) -> Role:
        role = self.get(role_id)
        if role.is_system:
            raise RoleImmutable("The admin role cannot be modified")
        if name is not None:
            name = name.strip()
            self._ensure_name_free(name, exclude_id=role.id)
            role.name = name
        if description is not None:
            role.description = description
        self.db.commit()
        self.db.refresh(role)
        return role

    def set_permissions(self, role_id: uuid.UUID, permissions: list[str]) -> Role:
        role = self.get(role_id)
        if role.is_system:
            raise RoleImmutable("The admin role's permissions cannot be changed")
        grants = self._validate_permissions(permissions)
        # full replace
        role.permissions.clear()
        self.db.flush()
        for perm in grants:
            self.db.add(RolePermission(role_id=role.id, permission=perm))
        self.db.commit()
        self.db.refresh(role)
        return role

    def delete(self, role_id: uuid.UUID) -> None:
        role = self.get(role_id)
        if role.is_system:
            raise RoleImmutable("The admin role cannot be deleted")
        if self.user_count(role.id) > 0:
            raise RoleInUse("Role is assigned to one or more users")
        self.db.delete(role)
        self.db.commit()

    # --- serialization -------------------------------------------------------

    def permissions_for(self, role: Role) -> list[str]:
        """Grant list for the API; the admin system role returns the ["*"] sentinel."""
        if role.is_system and role.slug == ADMIN_SLUG:
            return ["*"]
        return sorted(role.permission_keys)
