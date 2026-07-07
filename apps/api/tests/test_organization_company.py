"""Organization-as-branch API tests (feature 008): company_id/city persistence + grouping."""


def _create_company(client, name="Coffee Co"):
    resp = client.post("/api/companies", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_branch(client, company_id, *, url, city, name=None):
    payload = {"yandex_url": url, "city": city, "company_id": company_id}
    if name:
        payload["name"] = name
    resp = client.post("/api/organizations", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_branch_persists_company_and_city(admin_client):
    company_id = _create_company(admin_client)
    branch = _create_branch(
        admin_client, company_id, url="https://yandex.ru/maps/org/a/111/", city="Москва", name="Тверская, 17"
    )
    assert branch["company_id"] == company_id
    assert branch["city"] == "Москва"

    # Appears in the company's grouped branches under its city.
    grouped = admin_client.get(f"/api/companies/{company_id}/branches")
    assert grouped.status_code == 200
    groups = grouped.json()["groups"]
    assert any(g["city"] == "Москва" and g["branches"][0]["id"] == branch["id"] for g in groups)

    # branch_count reflects the assignment.
    assert admin_client.get(f"/api/companies/{company_id}").json()["branch_count"] == 1


def test_update_city_moves_group(admin_client):
    company_id = _create_company(admin_client)
    branch = _create_branch(admin_client, company_id, url="https://yandex.ru/maps/org/b/222/", city="Москва")

    patched = admin_client.patch(f"/api/organizations/{branch['id']}", json={"city": "СПб"})
    assert patched.status_code == 200
    assert patched.json()["city"] == "СПб"

    groups = admin_client.get(f"/api/companies/{company_id}/branches").json()["groups"]
    cities = [g["city"] for g in groups]
    assert "СПб" in cities and "Москва" not in cities


def test_create_branch_invalid_company(admin_client):
    resp = admin_client.post(
        "/api/organizations",
        json={
            "yandex_url": "https://yandex.ru/maps/org/c/333/",
            "company_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 422


def test_company_filter_on_org_list(admin_client):
    company_id = _create_company(admin_client)
    other_id = _create_company(admin_client, name="Other Co")
    _create_branch(admin_client, company_id, url="https://yandex.ru/maps/org/d/444/", city="Казань")
    _create_branch(admin_client, other_id, url="https://yandex.ru/maps/org/e/555/", city="Уфа")

    filtered = admin_client.get(f"/api/organizations?company_id={company_id}")
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert len(items) == 1
    assert items[0]["company_id"] == company_id
