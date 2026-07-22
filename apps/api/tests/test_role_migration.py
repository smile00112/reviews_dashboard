"""Migration continuity for feature 016 (User Story 4).

The pytest suite builds schema via ``Base.metadata.create_all`` rather than the
Alembic chain (older migrations use Postgres-only DDL), so this file validates the
*seed + legacy-mapping logic* that migration 0024 relies on, on SQLite. The Alembic
script itself is validated against a real Postgres per quickstart.md.
"""

from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLES, LEGACY_ROLE_MAP
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.services.permission_service import PermissionService
from app.services.role_service import map_legacy_role, seed_default_roles


def test_seed_creates_three_roles_with_grants(db_session):
    roles = seed_default_roles(db_session)
    assert set(roles) == {"admin", "call_center", "manager"}

    admin = roles["admin"]
    assert admin.is_system is True
    # admin stores no grant rows — full access comes from the shortcut
    assert admin.permission_keys == set()

    call_center = roles["call_center"]
    assert call_center.is_system is False
    assert "action:review.edit_status" in call_center.permission_keys
    assert "page:reviews" in call_center.permission_keys

    # every seeded grant is a real catalog key
    for spec in DEFAULT_ROLES:
        for grant in spec["grants"]:
            assert grant in ALL_PERMISSIONS


def test_seed_is_idempotent(db_session):
    first = seed_default_roles(db_session)
    second = seed_default_roles(db_session)
    assert first["admin"].id == second["admin"].id
    # no duplicate role rows
    from app.models.role import Role

    assert db_session.query(Role).count() == len(DEFAULT_ROLES)


def test_legacy_role_mapping():
    assert LEGACY_ROLE_MAP["admin"] == "admin"
    assert LEGACY_ROLE_MAP["review_operator"] == "call_center"
    assert map_legacy_role("admin") == "admin"
    assert map_legacy_role("review_operator") == "call_center"
    # unknown / null legacy values fall back to call_center so no user is role-less
    assert map_legacy_role(None) == "call_center"
    assert map_legacy_role("something_else") == "call_center"


def test_mapped_users_resolve_expected_access(db_session):
    """A pre-existing admin keeps full access; an operator lands on call_center."""
    roles = seed_default_roles(db_session)
    svc = PermissionService()

    legacy_admin = User(
        name="Legacy Admin",
        email="legacy_admin@test.com",
        role=UserRole.admin,
        role_id=roles[map_legacy_role("admin")].id,
        password_hash=hash_password("pw"),
        is_active=True,
    )
    legacy_op = User(
        name="Legacy Operator",
        email="legacy_op@test.com",
        role=UserRole.review_operator,
        role_id=roles[map_legacy_role("review_operator")].id,
        password_hash=hash_password("pw"),
        is_active=True,
    )
    db_session.add_all([legacy_admin, legacy_op])
    db_session.commit()

    # admin → full catalog
    assert svc.effective_permissions(legacy_admin) == set(ALL_PERMISSIONS.keys())
    # operator → call_center grants, no admin-only actions
    op_perms = svc.effective_permissions(legacy_op)
    assert "action:review.edit_status" in op_perms
    assert "action:roles.manage" not in op_perms
    assert "action:users.manage" not in op_perms
