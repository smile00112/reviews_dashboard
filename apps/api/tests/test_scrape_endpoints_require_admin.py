"""The scrape and operator-login endpoints must not be callable anonymously.

These four POSTs each spend real resources off the back of a single request:
they drive traffic at Yandex/2GIS from the server's IP, burn proxy credit, and
in the login case sign in with the operator's stored credentials. The panel is
reachable over a bare IP with no firewall in front of it, so an unauthenticated
caller could fire them in a loop and get the IP or the operator account flagged.

Reads stay open by design (the dashboard is read-only for operators) — this is
about the endpoints that act.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.enums import ScrapeMode
from app.models.organization import Organization


@pytest.fixture()
def organization(db_session):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/999/",
        normalized_url="https://yandex.ru/maps/org/test/999",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db_session.add(org)
    db_session.commit()
    return org


def test_scrape_organization_rejects_anonymous(client, organization):
    with patch("app.api.scrape_runs._run_scrape_background") as background:
        resp = client.post(f"/api/organizations/{organization.id}/scrape", json={"mode": "public"})
    assert resp.status_code == 401
    background.assert_not_called()


def test_scrape_all_rejects_anonymous(client):
    with patch("app.api.scrape_runs._run_scrape_background") as background:
        resp = client.post("/api/scrape/all", json={"mode": "public"})
    assert resp.status_code == 401
    background.assert_not_called()


def test_yandex_login_rejects_anonymous(client):
    with patch("app.api.scraper_sessions._run_login_background") as background:
        resp = client.post("/api/scraper/yandex/login")
    assert resp.status_code == 401
    background.assert_not_called()


def test_session_check_rejects_anonymous(client):
    with patch("app.api.scraper_sessions._run_check_background") as background:
        resp = client.post("/api/scraper/yandex/session/check")
    assert resp.status_code == 401
    background.assert_not_called()


def test_scrape_all_rejects_review_operator(operator_client):
    """A logged-in non-admin is authenticated but still must not trigger scrapes."""
    with patch("app.api.scrape_runs._run_scrape_background") as background:
        resp = operator_client.post("/api/scrape/all", json={"mode": "public"})
    assert resp.status_code == 403
    background.assert_not_called()


def test_yandex_login_rejects_review_operator(operator_client):
    with patch("app.api.scraper_sessions._run_login_background") as background:
        resp = operator_client.post("/api/scraper/yandex/login")
    assert resp.status_code == 403
    background.assert_not_called()


def test_unknown_organization_still_rejects_anonymous_before_404(client):
    """Auth is checked before existence, so the endpoint can't be used to probe IDs."""
    with patch("app.api.scrape_runs._run_scrape_background"):
        resp = client.post(f"/api/organizations/{uuid4()}/scrape", json={"mode": "public"})
    assert resp.status_code == 401
