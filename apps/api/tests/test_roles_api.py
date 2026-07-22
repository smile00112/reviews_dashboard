"""Roles management API + guards (feature 016, User Story 3)."""

import uuid


def _role_by_slug(client, slug):
    roles = client.get("/api/roles").json()
    return next((r for r in roles if r["slug"] == slug), None)


# --- auth on the router ------------------------------------------------------


def test_catalog_requires_permission(operator_client):
    # call_center lacks action:roles.manage
    assert operator_client.get("/api/roles/catalog").status_code == 403


def test_catalog_anonymous_401(client):
    assert client.get("/api/roles/catalog").status_code == 401


def test_catalog_has_pages_actions_and_no_reply(admin_client):
    body = admin_client.get("/api/roles/catalog").json()
    keys = {i["key"] for i in body["pages"]} | {i["key"] for i in body["actions"]}
    assert "page:reviews" in keys
    assert "action:roles.manage" in keys
    assert not any("reply" in k for k in keys)


# --- list --------------------------------------------------------------------


def test_list_roles_shape(admin_client):
    roles = admin_client.get("/api/roles").json()
    by_slug = {r["slug"]: r for r in roles}
    assert set(by_slug) >= {"admin", "call_center", "manager"}
    # admin reports the ["*"] sentinel and is a system role
    assert by_slug["admin"]["permissions"] == ["*"]
    assert by_slug["admin"]["is_system"] is True
    # admin + call_center each have ≥1 user from seed_users
    assert by_slug["admin"]["user_count"] == 1
    assert by_slug["call_center"]["user_count"] == 1
    assert "action:review.edit_status" in by_slug["call_center"]["permissions"]


# --- create ------------------------------------------------------------------


def test_create_role(admin_client):
    resp = admin_client.post(
        "/api/roles",
        json={"name": "Аналитик", "permissions": ["page:overview", "page:ratings"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "analitik"
    assert set(body["permissions"]) == {"page:overview", "page:ratings"}
    assert body["is_system"] is False
    assert body["user_count"] == 0


def test_create_duplicate_name_409(admin_client):
    admin_client.post("/api/roles", json={"name": "Дубль"})
    resp = admin_client.post("/api/roles", json={"name": "Дубль"})
    assert resp.status_code == 409


def test_create_blank_name_422(admin_client):
    assert admin_client.post("/api/roles", json={"name": "   "}).status_code == 422


def test_create_unknown_permission_422(admin_client):
    resp = admin_client.post(
        "/api/roles", json={"name": "BadPerms", "permissions": ["page:does_not_exist"]}
    )
    assert resp.status_code == 422


# --- update / grants ---------------------------------------------------------


def test_rename_role(admin_client):
    created = admin_client.post("/api/roles", json={"name": "Старое имя"}).json()
    resp = admin_client.patch(f"/api/roles/{created['id']}", json={"name": "Новое имя"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Новое имя"


def test_cannot_rename_admin(admin_client):
    admin = _role_by_slug(admin_client, "admin")
    resp = admin_client.patch(f"/api/roles/{admin['id']}", json={"name": "Root"})
    assert resp.status_code == 403


def test_set_permissions_full_replace(admin_client):
    created = admin_client.post(
        "/api/roles", json={"name": "Гранты", "permissions": ["page:overview"]}
    ).json()
    resp = admin_client.put(
        f"/api/roles/{created['id']}/permissions",
        json={"permissions": ["page:reviews", "action:review.edit_status"]},
    )
    assert resp.status_code == 200
    assert set(resp.json()["permissions"]) == {"page:reviews", "action:review.edit_status"}


def test_cannot_edit_admin_permissions(admin_client):
    admin = _role_by_slug(admin_client, "admin")
    resp = admin_client.put(
        f"/api/roles/{admin['id']}/permissions", json={"permissions": ["page:overview"]}
    )
    assert resp.status_code == 403


def test_set_permissions_unknown_422(admin_client):
    created = admin_client.post("/api/roles", json={"name": "Гранты2"}).json()
    resp = admin_client.put(
        f"/api/roles/{created['id']}/permissions", json={"permissions": ["nope"]}
    )
    assert resp.status_code == 422


# --- delete ------------------------------------------------------------------


def test_delete_unused_role(admin_client):
    created = admin_client.post("/api/roles", json={"name": "Временная"}).json()
    assert admin_client.delete(f"/api/roles/{created['id']}").status_code == 204
    assert _role_by_slug(admin_client, created["slug"]) is None


def test_cannot_delete_admin(admin_client):
    admin = _role_by_slug(admin_client, "admin")
    assert admin_client.delete(f"/api/roles/{admin['id']}").status_code == 403


def test_cannot_delete_role_in_use(admin_client):
    # call_center is assigned to the seeded operator user
    call_center = _role_by_slug(admin_client, "call_center")
    resp = admin_client.delete(f"/api/roles/{call_center['id']}")
    assert resp.status_code == 409


def test_delete_unknown_404(admin_client):
    assert admin_client.delete(f"/api/roles/{uuid.uuid4()}").status_code == 404
