"""Admin panel RBAC tests (feature 004).

Tests that admin role has full access and review_operator is restricted
per the RBAC matrix in specs/004-admin-panel/plan.md.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ADMIN_SECRET_KEY", "test-secret-key-not-for-production")

from app.core.database import Base, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_REDIRECT_CODES = (301, 302, 303, 307, 308)


@pytest.fixture(scope="module")
def rbac_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def rbac_session(rbac_engine):
    from app.services.role_service import seed_default_roles

    Session = sessionmaker(bind=rbac_engine)
    db = Session()
    roles = seed_default_roles(db)
    db.add_all([
        User(
            name="Admin",
            email="rbac_admin@test.com",
            role=UserRole.admin,
            role_id=roles["admin"].id,
            password_hash=hash_password("adminpass"),
            is_active=True,
        ),
        User(
            name="Operator",
            email="rbac_op@test.com",
            role=UserRole.review_operator,
            role_id=roles["call_center"].id,
            password_hash=hash_password("oppass"),
            is_active=True,
        ),
    ])
    db.commit()
    db.close()
    return Session


def _make_client(rbac_session, monkeypatch) -> TestClient:
    import app.admin.auth as auth_module

    monkeypatch.setattr(auth_module, "SessionLocal", rbac_session)

    from app.main import app

    def _override_get_db():
        db = rbac_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app, follow_redirects=False)


def _logged_in_client(rbac_session, monkeypatch, email: str, password: str) -> TestClient:
    """Return a TestClient with an active login session."""
    client = _make_client(rbac_session, monkeypatch)
    r = client.post("/admin/login", data={"username": email, "password": password})
    assert r.status_code in _REDIRECT_CODES, f"Login failed for {email}: {r.status_code}"
    return client


@pytest.fixture()
def admin_client(rbac_session, monkeypatch):
    c = _logged_in_client(rbac_session, monkeypatch, "rbac_admin@test.com", "adminpass")
    yield c
    from app.main import app
    app.dependency_overrides.clear()


@pytest.fixture()
def op_client(rbac_session, monkeypatch):
    c = _logged_in_client(rbac_session, monkeypatch, "rbac_op@test.com", "oppass")
    yield c
    from app.main import app
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Operator restrictions
# --------------------------------------------------------------------------- #

def test_operator_no_users_access(op_client):
    r = op_client.get("/admin/user/list")
    # Operator must NOT reach the Users list — redirect or 403.
    assert r.status_code in (*_REDIRECT_CODES, 403)
    # Must NOT be a 200 (access granted).
    assert r.status_code != 200


def test_operator_org_read_only(op_client):
    r = op_client.get("/admin/organization/list")
    # List must be accessible to operator (200).
    assert r.status_code == 200


def test_operator_cannot_create_review(op_client):
    r = op_client.get("/admin/review/create")
    # Operator must NOT reach the create form — redirect or 403.
    assert r.status_code in (*_REDIRECT_CODES, 403)
    assert r.status_code != 200


# --------------------------------------------------------------------------- #
# Admin access
# --------------------------------------------------------------------------- #

def test_admin_can_access_users(admin_client):
    r = admin_client.get("/admin/user/list")
    assert r.status_code == 200


def test_admin_can_access_orgs(admin_client):
    r = admin_client.get("/admin/organization/list")
    assert r.status_code == 200


def test_admin_can_access_reviews(admin_client):
    r = admin_client.get("/admin/review/list")
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# Seed idempotency
# --------------------------------------------------------------------------- #

def test_seed_idempotent():
    from app.scripts.seed_users import _seed

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    _seed(db, "seed@test.com", "Seeded", UserRole.admin, "admin", "seedpass")
    _seed(db, "seed@test.com", "Seeded", UserRole.admin, "admin", "seedpass")  # idempotent

    count = db.query(User).filter(User.email == "seed@test.com").count()
    assert count == 1

    user = db.query(User).filter(User.email == "seed@test.com").first()
    assert user.password_hash != "seedpass"  # stored as bcrypt hash

    db.close()
    Base.metadata.drop_all(engine)
