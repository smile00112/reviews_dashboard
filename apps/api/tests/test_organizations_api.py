def test_create_list_update_delete_organization(client):
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
    assert org["last_scrape_status"] == "pending"

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


def test_update_organization_map_links(client):
    create_resp = client.post(
        "/api/organizations",
        json={
            "yandex_url": "https://yandex.ru/maps/org/test/987654321/",
            "preferred_scrape_mode": "public",
        },
    )
    assert create_resp.status_code == 201
    org_id = create_resp.json()["id"]

    # Set both links.
    set_resp = client.patch(
        f"/api/organizations/{org_id}",
        json={
            "twogis_url": "https://go.2gis.com/abc12",
            "google_url": "https://maps.app.goo.gl/xyz34",
        },
    )
    assert set_resp.status_code == 200
    body = set_resp.json()
    assert body["twogis_url"] == "https://go.2gis.com/abc12"
    assert body["google_url"] == "https://maps.app.goo.gl/xyz34"

    # Absent field leaves the link unchanged; present empty string clears it.
    partial_resp = client.patch(
        f"/api/organizations/{org_id}",
        json={"twogis_url": ""},
    )
    assert partial_resp.status_code == 200
    partial = partial_resp.json()
    assert partial["twogis_url"] is None
    assert partial["google_url"] == "https://maps.app.goo.gl/xyz34"


def test_create_organization_invalid_url(client):
    resp = client.post(
        "/api/organizations",
        json={"yandex_url": "https://google.com/maps/place/test"},
    )
    assert resp.status_code == 422
