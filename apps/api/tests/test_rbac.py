"""RBAC tests (feature 008): admin writes vs review_operator read-only."""

VALID_URL = "https://yandex.ru/maps/org/test/123456789/"


def test_operator_can_read_but_not_write_companies(operator_client):
    # Read allowed.
    assert operator_client.get("/api/companies").status_code == 200
    # Writes forbidden.
    assert operator_client.post("/api/companies", json={"name": "X"}).status_code == 403


def test_operator_cannot_write_organizations(operator_client):
    assert operator_client.post("/api/organizations", json={"yandex_url": VALID_URL}).status_code == 403


def test_unauthenticated_cannot_read_companies(client):
    assert client.get("/api/companies").status_code == 401


def test_unauthenticated_cannot_write(client):
    assert client.post("/api/companies", json={"name": "X"}).status_code == 401
    assert client.post("/api/organizations", json={"yandex_url": VALID_URL}).status_code == 401


def test_admin_can_write_company(admin_client):
    assert admin_client.post("/api/companies", json={"name": "Coffee Co"}).status_code == 201
