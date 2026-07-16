from unittest.mock import MagicMock, patch

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService


def test_scrape_run_creation_and_execution(client, db_session):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db_session.add(org)
    db_session.commit()

    mock_result = ScrapeResult(
        organization=ParsedOrganization(name="Test", rating=4.5, review_count=1),
        reviews=[ParsedReview(author_name="User", rating=5, review_text="Nice", review_date_text="today")],
    )
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = mock_result

    service = ScrapeService(db_session, public_scraper=mock_scraper)
    run = service.create_run(org.id, ScrapeMode.public)
    service.execute_run(run.id)

    assert run.status.value == "success"
    assert run.reviews_inserted == 1

    list_resp = client.get("/api/scrape-runs")
    assert list_resp.status_code == 200
    assert any(item["id"] == str(run.id) for item in list_resp.json()["items"])

    detail_resp = client.get(f"/api/scrape-runs/{run.id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "success"


def test_scrape_endpoint_accepts_request(admin_client, db_session):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/456/",
        normalized_url="https://yandex.ru/maps/org/test/456",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db_session.add(org)
    db_session.commit()

    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = ScrapeResult(reviews=[])

    with patch("app.api.scrape_runs._run_scrape_background") as background:
        resp = admin_client.post(f"/api/organizations/{org.id}/scrape", json={"mode": "public"})
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        background.assert_called_once()
