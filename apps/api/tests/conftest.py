import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Must be set before any app.* imports so pydantic-settings can instantiate Settings.
os.environ.setdefault("ADMIN_SECRET_KEY", "test-secret-key-not-for-production")

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- Auth fixtures (feature 008) ---------------------------------------------

ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "adminpass"
OPERATOR_EMAIL = "op@test.com"
OPERATOR_PASSWORD = "oppass"


@pytest.fixture()
def seed_users(db_session):
    """Seed one admin and one review_operator into the test DB."""
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    admin = User(
        name="Admin User",
        email=ADMIN_EMAIL,
        role=UserRole.admin,
        password_hash=hash_password(ADMIN_PASSWORD),
        is_active=True,
    )
    operator = User(
        name="Op User",
        email=OPERATOR_EMAIL,
        role=UserRole.review_operator,
        password_hash=hash_password(OPERATOR_PASSWORD),
        is_active=True,
    )
    db_session.add_all([admin, operator])
    db_session.commit()
    return {"admin": admin, "operator": operator}


@pytest.fixture()
def admin_client(client, seed_users):
    """TestClient authenticated as an admin (session cookie set)."""
    resp = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture()
def operator_client(client, seed_users):
    """TestClient authenticated as a read-only review_operator."""
    resp = client.post("/api/auth/login", json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD})
    assert resp.status_code == 200, resp.text
    return client
