"""Auth API tests (feature 008): login / me / logout via session cookie."""

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_login_success_and_me(client, seed_users):
    resp = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"]["slug"] == "admin"
    assert body["role"]["is_system"] is True
    # admin resolves to the full catalog
    assert "action:roles.manage" in body["permissions"]
    assert "password" not in body and "password_hash" not in body

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


def test_login_wrong_password(client, seed_users):
    resp = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "nope"})
    assert resp.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_unknown_email(client, seed_users):
    resp = client.post("/api/auth/login", json={"email": "ghost@test.com", "password": "x"})
    assert resp.status_code == 401


def test_me_requires_session(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_clears_session(client, seed_users):
    assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_inactive_user(client, db_session):
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User
    from app.services.role_service import seed_default_roles

    roles = seed_default_roles(db_session)
    db_session.add(
        User(
            name="Inactive",
            email="inactive@test.com",
            role=UserRole.admin,
            role_id=roles["admin"].id,
            password_hash=hash_password("pw"),
            is_active=False,
        )
    )
    db_session.commit()
    resp = client.post("/api/auth/login", json={"email": "inactive@test.com", "password": "pw"})
    assert resp.status_code == 403
