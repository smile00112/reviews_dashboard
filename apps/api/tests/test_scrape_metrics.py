"""Unit tests for the bulk metrics-only scraper CLI (scripts/scrape_metrics.py).

No network: a fake scraper is injected and orchestration (run()) is exercised
against in-memory Organization rows via a fake session. Verifies --only-missing,
--dry-run, and the no-url skip. Per-platform column routing, the null-value
guard, and manual-action handling now live in MetricsService and are covered
by tests/test_metrics_service.py — not duplicated here.
"""

from __future__ import annotations

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
