"""Role lifecycle + seeding for the RBAC system (feature 016).

This module hosts the seed helper used by the seed-users script and tests. The
full admin-facing CRUD (create/rename/grants/delete with guards) is added in the
User Story 3 phase.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLES, LEGACY_ROLE_MAP
from app.models.role import Role, RolePermission


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
