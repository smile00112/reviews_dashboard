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


def test_create_organization_invalid_url(client):
    resp = client.post(
        "/api/organizations",
        json={"yandex_url": "https://google.com/maps/place/test"},
    )
    assert resp.status_code == 422
