"""GET /api/auth/me exposes role + effective permissions (feature 016).

The frontend mirrors this set for UX; it must be exact per role.
"""

from app.core.permissions import ALL_PERMISSIONS
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, OPERATOR_EMAIL, OPERATOR_PASSWORD

CALL_CENTER_EXPECTED = {
    "page:overview",
    "page:ratings",
    "page:reviews",
    "action:review.edit_status",
}


def test_me_admin_returns_full_catalog(admin_client):
    body = admin_client.get("/api/auth/me").json()
    assert body["role"]["slug"] == "admin"
    assert body["role"]["is_system"] is True
    assert set(body["permissions"]) == set(ALL_PERMISSIONS.keys())


def test_me_call_center_returns_exact_grants(operator_client):
    body = operator_client.get("/api/auth/me").json()
    assert body["role"]["slug"] == "call_center"
    assert body["role"]["is_system"] is False
    assert set(body["permissions"]) == CALL_CENTER_EXPECTED
    # explicitly denied admin-side actions are absent
    assert "action:roles.manage" not in body["permissions"]
    assert "action:scrape.run" not in body["permissions"]


def test_login_returns_permissions(client, seed_users):
    body = client.post(
        "/api/auth/login", json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD}
    ).json()
    assert set(body["permissions"]) == CALL_CENTER_EXPECTED

    admin_body = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    ).json()
    assert "action:roles.manage" in admin_body["permissions"]
