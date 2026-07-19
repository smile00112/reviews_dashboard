def test_create_list_update_delete_organization(admin_client):
    client = admin_client
    create_resp = client.post(
        "/api/organizations",
        json={
            "yandex_url": "https://yandex.ru/maps/org/test/123456789/",
            "preferred_scrape_mode": "public",
        },
    )
    assert create_resp.status_code == 201
    org = create_resp.json()
    org_id = org["id"]
    assert org["yandex_scrape_status"] == "pending"
    assert org["gis2_scrape_status"] == "pending"

    list_resp = client.get("/api/organizations")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1

    patch_resp = client.patch(
        f"/api/organizations/{org_id}",
        json={"preferred_scrape_mode": "operator_auth", "name": "Test Org"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["preferred_scrape_mode"] == "operator_auth"
    assert patch_resp.json()["name"] == "Test Org"

    delete_resp = client.delete(f"/api/organizations/{org_id}")
    assert delete_resp.status_code == 204

    list_after = client.get("/api/organizations")
    assert len(list_after.json()["items"]) == 0


def test_list_organizations_pagination(client, db_session):
    """limit/offset page the list; total is the full count, not the page size."""
    from app.models.organization import Organization

    for i in range(5):
        db_session.add(Organization(name=f"Org {i}", gis2_url=f"https://2gis.ru/firm/{i}"))
    db_session.commit()

    # Unpaged: total == number of items returned (backward compatible).
    full = client.get("/api/organizations").json()
    assert len(full["items"]) == 5
    assert full["total"] == 5

    # First page.
    page1 = client.get("/api/organizations?limit=2&offset=0").json()
    assert len(page1["items"]) == 2
    assert page1["total"] == 5

    # Second page — disjoint from the first (stable created_at desc order).
    page2 = client.get("/api/organizations?limit=2&offset=2").json()
    assert len(page2["items"]) == 2
    ids1 = {o["id"] for o in page1["items"]}
    ids2 = {o["id"] for o in page2["items"]}
    assert ids1.isdisjoint(ids2)

    # Tail page — fewer than limit, total unchanged.
    page3 = client.get("/api/organizations?limit=2&offset=4").json()
    assert len(page3["items"]) == 1
    assert page3["total"] == 5


def test_list_organizations_includes_gis2_only_org(client, db_session):
    """2GIS-only orgs have no yandex_url/normalized_url; the list endpoint
    must serialize them instead of failing with 500 (regression)."""
    from app.models.organization import Organization

    db_session.add(Organization(name="2GIS only", gis2_url="https://2gis.ru/firm/123"))
    db_session.commit()

    resp = client.get("/api/organizations")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["yandex_url"] is None
    assert items[0]["normalized_url"] is None


def test_create_organization_invalid_url(admin_client):
    resp = admin_client.post(
        "/api/organizations",
        json={"yandex_url": "https://google.com/maps/place/test"},
    )
    assert resp.status_code == 422


def test_create_organization_requires_admin(client):
    """Unauthenticated create is rejected (feature 008 guard)."""
    resp = client.post(
        "/api/organizations",
        json={"yandex_url": "https://yandex.ru/maps/org/test/123456789/"},
    )
    assert resp.status_code == 401
