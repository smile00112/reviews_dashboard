"""Unit tests for the bulk metrics-only scraper CLI (scripts/scrape_metrics.py).

No network: a fake scraper is injected and the persist/routing logic is exercised
against in-memory Organization rows. Verifies per-platform column routing, the
null-value guard, --only-missing, and --dry-run.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.models.organization import Organization
from app.scraper.types import ParsedOrganization, ScrapeResult
from scripts import scrape_metrics


def _result(rating=None, review_count=None, rating_count=None, error_code=None, manual=False):
    return ScrapeResult(
        organization=ParsedOrganization(
            rating=rating, review_count=review_count, rating_count=rating_count
        ),
        needs_manual_action=manual,
        error_code=error_code,
    )


def _org(**kw):
    org = Organization()
    for k, v in kw.items():
        setattr(org, k, v)
    return org


def test_yandex_result_routes_to_yandex_columns():
    org = _org()
    summary = scrape_metrics.PlatformSummary()
    outcome = scrape_metrics.apply_result(
        org, "yandex", _result(rating=4.9, review_count=164, rating_count=230), summary
    )
    assert outcome == "updated"
    assert org.rating == 4.9
    assert org.review_count == 164
    assert org.yandex_rating_count == 230
    # 2GIS columns untouched.
    assert org.gis2_rating is None
    assert summary.updated == 1


def test_2gis_result_routes_to_gis2_columns():
    org = _org(rating=4.9, review_count=164)  # existing Yandex values
    summary = scrape_metrics.PlatformSummary()
    scrape_metrics.apply_result(org, "2gis", _result(rating=4.2, review_count=1179), summary)
    assert org.gis2_rating == 4.2
    assert org.gis2_review_count == 1179
    # Yandex values must not be clobbered by a 2GIS scrape.
    assert org.rating == 4.9
    assert org.review_count == 164


def test_null_rating_is_failure_and_never_overwrites():
    org = _org(rating=4.5, review_count=10)
    summary = scrape_metrics.PlatformSummary()
    outcome = scrape_metrics.apply_result(org, "yandex", _result(rating=None), summary)
    assert outcome == "failed"
    assert org.rating == 4.5  # preserved
    assert org.review_count == 10
    assert summary.failed == 1


def test_missing_review_count_keeps_existing_count():
    org = _org(review_count=99)
    summary = scrape_metrics.PlatformSummary()
    scrape_metrics.apply_result(org, "yandex", _result(rating=4.0, review_count=None), summary)
    assert org.rating == 4.0
    assert org.review_count == 99  # not overwritten with null


def test_manual_action_counts_and_skips_write():
    org = _org()
    summary = scrape_metrics.PlatformSummary()
    outcome = scrape_metrics.apply_result(org, "2gis", _result(manual=True), summary)
    assert outcome == "manual_action"
    assert org.gis2_rating is None
    assert summary.manual_action == 1


class _FakeSession:
    """Minimal Session stand-in: serves a fixed org list, records commit/rollback."""

    def __init__(self, orgs):
        self._orgs = orgs
        self.commits = 0
        self.rolledback = False

    def query(self, *_):
        return self

    def order_by(self, *_):
        return self

    def limit(self, _n):
        return self

    def all(self):
        return self._orgs

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolledback = True


class _FakeScrapers:
    def __init__(self, mapping):
        self._mapping = mapping  # platform -> ScrapeResult

    def scrape(self, platform, _url):
        return self._mapping[platform]


def test_only_missing_skips_populated_metric():
    org = _org(yandex_url="u", rating=4.4)
    session = _FakeSession([org])
    scrapers = _FakeScrapers({"yandex": _result(rating=1.0)})
    summary = scrape_metrics.run(
        session, scrapers, ["yandex"], limit=1, only_missing=True, dry_run=False
    )
    assert summary.get("yandex").skipped == 1
    assert org.rating == 4.4  # untouched


def test_dry_run_rolls_back_and_never_commits():
    org = _org(yandex_url="u")
    session = _FakeSession([org])
    scrapers = _FakeScrapers({"yandex": _result(rating=4.1, review_count=5)})
    scrape_metrics.run(session, scrapers, ["yandex"], limit=1, only_missing=False, dry_run=True)
    assert session.rolledback is True
    assert session.commits == 0


def test_no_url_is_skipped():
    org = _org(yandex_url=None)
    session = _FakeSession([org])
    scrapers = _FakeScrapers({"yandex": _result(rating=4.1)})
    summary = scrape_metrics.run(
        session, scrapers, ["yandex"], limit=1, only_missing=False, dry_run=False
    )
    assert summary.get("yandex").skipped == 1
