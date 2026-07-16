"""Platform URL selection: each scrape mode must follow its own platform's link.

Regression cover for a bug where ScrapeService handed org.yandex_url to every mode,
so a twogis_api run silently scraped the Yandex URL (and, with no gis2_url set,
scraped a link the operator never pointed at 2GIS).
"""

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService, _mode_url

YANDEX_URL = "https://yandex.ru/maps/org/test/123/reviews/"
GIS2_URL = "https://2gis.ru/firm/456"


class UrlRecordingScraper:
    """Records the URL it was handed; returns a fixed successful result."""

    def __init__(self):
        self.urls = []

    def scrape(self, url, *args, **kwargs):
        self.urls.append(url)
        return ScrapeResult(
            organization=ParsedOrganization(name="Кафе Пример", rating=4.3, review_count=1),
            reviews=[
                ParsedReview(author_name="Анна", rating=5, review_text="Очень вкусно", review_date_text="1 мая"),
            ],
        )


def _org(db, *, yandex_url=YANDEX_URL, gis2_url=GIS2_URL):
    org = Organization(
        yandex_url=yandex_url,
        gis2_url=gis2_url,
        preferred_scrape_mode=ScrapeMode.public,
    )
    db.add(org)
    db.commit()
    return org


def test_mode_url_picks_gis2_url_for_twogis_api(db_session):
    org = _org(db_session)
    assert _mode_url(org, ScrapeMode.twogis_api) == GIS2_URL


def test_mode_url_picks_yandex_url_for_yandex_modes(db_session):
    org = _org(db_session)
    for mode in (ScrapeMode.public, ScrapeMode.public_http, ScrapeMode.scrapeops, ScrapeMode.operator_auth):
        assert _mode_url(org, mode) == YANDEX_URL


def test_twogis_run_scrapes_the_gis2_url_not_the_yandex_one(db_session):
    org = _org(db_session)
    twogis = UrlRecordingScraper()
    service = ScrapeService(db_session, twogis_scraper=twogis)

    run = service.create_run(org.id, ScrapeMode.twogis_api)
    service.execute_run(run.id)

    assert twogis.urls == [GIS2_URL]
    assert service.get_run(run.id).status.value == "success"


def test_missing_platform_url_fails_without_calling_the_scraper(db_session):
    org = _org(db_session, gis2_url=None)
    twogis = UrlRecordingScraper()
    service = ScrapeService(db_session, twogis_scraper=twogis)

    run = service.create_run(org.id, ScrapeMode.twogis_api)
    service.execute_run(run.id)

    assert twogis.urls == []
    run = service.get_run(run.id)
    assert run.status.value == "failed"
    assert run.error_code == "no_url"
