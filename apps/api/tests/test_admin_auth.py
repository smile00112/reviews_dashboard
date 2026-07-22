"""Admin panel authentication tests (feature 004).

Uses SQLite in-memory DB with seeded test users. Patches app.admin.auth.SessionLocal
so the AdminAuth backend queries SQLite instead of Postgres.
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
def admin_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def seeded_session(admin_engine):
    """Module-scoped SQLite session with seeded admin/operator/inactive users."""
    from app.services.role_service import seed_default_roles

    Session = sessionmaker(bind=admin_engine)
    db = Session()
    roles = seed_default_roles(db)
    db.add_all([
        User(
            name="Admin User",
            email="admin@test.com",
            role=UserRole.admin,
            role_id=roles["admin"].id,
            password_hash=hash_password("adminpass"),
            is_active=True,
        ),
        User(
            name="Op User",
            email="op@test.com",
            role=UserRole.review_operator,
            role_id=roles["call_center"].id,
            password_hash=hash_password("oppass"),
            is_active=True,
        ),
        User(
            name="Inactive",
            email="inactive@test.com",
            role=UserRole.admin,
            role_id=roles["admin"].id,
            password_hash=hash_password("inactivepass"),
            is_active=False,
        ),
    ])
    db.commit()
    db.close()
    return Session


@pytest.fixture()
def client(seeded_session, monkeypatch):
    """TestClient with AdminAuth patched to use the SQLite test session."""
    import app.admin.auth as auth_module

    monkeypatch.setattr(auth_module, "SessionLocal", seeded_session)

    from app.main import app

    def _override_get_db():
        db = seeded_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, email: str, password: str):
    return client.post(
        "/admin/login",
        data={"username": email, "password": password},
    )


def test_unauthenticated_redirect(client):
    # /admin may redirect to /admin/ (trailing-slash), then to /admin/login.
    # Follow one hop to reach the auth redirect.
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code in _REDIRECT_CODES
    assert "login" in r.headers["location"]


def test_login_success(client):
    r = _login(client, "admin@test.com", "adminpass")
    assert r.status_code in _REDIRECT_CODES
    loc = r.headers["location"]
    # Location may be full URL (http://testserver/admin/) or path (/admin/).
    assert loc.rstrip("/").endswith("/admin")


def test_login_wrong_password(client):
    r = _login(client, "admin@test.com", "wrongpassword")
    # sqladmin returns 400 on failed authentication.
    assert r.status_code in (200, 400)


def test_login_inactive_user(client):
    r = _login(client, "inactive@test.com", "inactivepass")
    assert r.status_code in (200, 400)


def test_logout_clears_session(client):
    # Login first.
    r = _login(client, "admin@test.com", "adminpass")
    assert r.status_code in _REDIRECT_CODES

    # Logout.
    r = client.get("/admin/logout")
    assert r.status_code in _REDIRECT_CODES

    # After logout, /admin/ must redirect to login (not serve dashboard).
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code in _REDIRECT_CODES
    assert "login" in r.headers["location"]
