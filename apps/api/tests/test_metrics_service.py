from decimal import Decimal

from app.models.enums import OrganizationScrapeStatus
from app.models.organization import Organization
from app.scraper.types import ParsedOrganization, ScrapeResult
from app.services.metrics_service import MetricsOutcome, MetricsService


class FakeScrapers:
    def __init__(self, result: ScrapeResult):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def scrape(self, platform: str, url: str) -> ScrapeResult:
        self.calls.append((platform, url))
        return self.result


def _result(rating=None, review_count=None, rating_count=None, error_code=None, manual=False):
    return ScrapeResult(
        organization=ParsedOrganization(
            rating=rating, review_count=review_count, rating_count=rating_count
        ),
        reviews=[],
        needs_manual_action=manual,
        error_code=error_code,
    )


def test_refresh_writes_yandex_columns(db_session):
    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1", rating=Decimal("4.0"))
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(4.7, 120, 340)))
    result = service.refresh_organization(org, "yandex")
    db_session.commit()

    assert result.outcome is MetricsOutcome.updated
    assert float(org.rating) == 4.7
    assert org.review_count == 120
    assert org.yandex_rating_count == 340
    assert org.yandex_scrape_status == OrganizationScrapeStatus.success
    assert org.yandex_last_successful_scrape_at is not None
    assert result.payload["rating_before"] == 4.0
    assert result.payload["rating_after"] == 4.7


def test_refresh_never_wipes_known_value_on_failure(db_session):
    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1", rating=Decimal("4.2"), review_count=99)
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(rating=None, error_code="http_500")))
    result = service.refresh_organization(org, "yandex")
    db_session.commit()

    assert result.outcome is MetricsOutcome.failed
    assert result.error_code == "http_500"
    assert float(org.rating) == 4.2
    assert org.review_count == 99
    assert org.yandex_scrape_status == OrganizationScrapeStatus.failed


def test_refresh_marks_manual_action(db_session):
    org = Organization(name="Org", gis2_url="https://2gis.ru/firm/1")
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(manual=True)))
    result = service.refresh_organization(org, "2gis")
    db_session.commit()

    assert result.outcome is MetricsOutcome.manual_action
    assert org.gis2_scrape_status == OrganizationScrapeStatus.needs_manual_action


def test_refresh_writes_2gis_columns_without_touching_yandex(db_session):
    org = Organization(
        name="Org",
        gis2_url="https://2gis.ru/firm/1",
        rating=Decimal("4.9"),
        review_count=164,
        yandex_rating_count=230,
    )
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(4.2, 1179, 1500)))
    result = service.refresh_organization(org, "2gis")
    db_session.commit()

    assert result.outcome is MetricsOutcome.updated
    assert float(org.gis2_rating) == 4.2
    assert org.gis2_review_count == 1179
    assert org.gis2_rating_count == 1500
    assert org.gis2_scrape_status == OrganizationScrapeStatus.success
    assert org.gis2_last_successful_scrape_at is not None
    # Yandex columns untouched by a 2GIS scrape.
    assert float(org.rating) == 4.9
    assert org.review_count == 164
    assert org.yandex_rating_count == 230


def test_refresh_missing_counts_keep_existing_values(db_session):
    org = Organization(
        name="Org",
        yandex_url="https://yandex.ru/maps/org/1",
        rating=Decimal("4.0"),
        review_count=99,
        yandex_rating_count=150,
    )
    db_session.add(org)
    db_session.commit()

    service = MetricsService(
        db_session, scrapers=FakeScrapers(_result(rating=4.5, review_count=None, rating_count=None))
    )
    result = service.refresh_organization(org, "yandex")
    db_session.commit()

    assert result.outcome is MetricsOutcome.updated
    assert float(org.rating) == 4.5
    # Existing counts preserved: a scrape must never overwrite a known value with null.
    assert org.review_count == 99
    assert org.yandex_rating_count == 150
