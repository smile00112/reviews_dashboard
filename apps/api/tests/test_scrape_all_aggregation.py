"""Feature 010 / US2: parent run of /scrape/all aggregates child outcomes."""

from uuid import uuid4

import pytest

from app.models.enums import ScrapeMode, ScrapeRunStatus
from app.models.organization import Organization
from app.models.scrape_run import ScrapeRun
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService


def _orgs(db, n):
    orgs = [Organization(yandex_url=f"https://yandex.ru/maps/org/o{i}/{i}/") for i in range(n)]
    db.add_all(orgs)
    db.commit()
    return orgs


def _ok_result(reviews=1):
    return ScrapeResult(
        organization=ParsedOrganization(name="Org"),
        reviews=[
            ParsedReview(
                author_name=f"A{i}-{uuid4().hex[:6]}",
                rating=5,
                review_text=f"text {uuid4().hex}",
                review_date_text="1 июня",
            )
            for i in range(reviews)
        ],
    )


def _captcha_result():
    r = ScrapeResult()
    r.needs_manual_action = True
    r.error_code = "access_challenge"
    r.error_message = "captcha"
    return r


def _failed_result():
    r = ScrapeResult()
    r.error_code = "boom"
    r.error_message = "failed"
    return r


class _StubScraper:
    """Returns pre-baked results in org order."""

    def __init__(self, results):
        self._results = list(results)
        self._i = 0

    def scrape(self, url):
        result = self._results[self._i % len(self._results)]
        self._i += 1
        if isinstance(result, Exception):
            raise result
        return result


def _run_all(db, results) -> ScrapeRun:
    service = ScrapeService(db)
    service.public_scraper = _StubScraper(results)
    run = service.create_run(None, ScrapeMode.public)
    service.execute_run(run.id)
    db.refresh(run)
    return run


def test_all_failed_children_fail_parent(db_session):
    _orgs(db_session, 3)
    run = _run_all(db_session, [_failed_result()])
    assert run.status == ScrapeRunStatus.failed


def test_all_captcha_children_mark_parent_needs_manual_action(db_session):
    _orgs(db_session, 3)
    run = _run_all(db_session, [_captcha_result()])
    assert run.status == ScrapeRunStatus.needs_manual_action


def test_mixed_failed_and_captcha_prefers_needs_manual_action(db_session):
    _orgs(db_session, 2)
    run = _run_all(db_session, [_failed_result(), _captcha_result()])
    assert run.status == ScrapeRunStatus.needs_manual_action


def test_any_success_makes_parent_success_with_rolled_up_counters(db_session):
    _orgs(db_session, 3)
    run = _run_all(db_session, [_ok_result(2), _failed_result(), _ok_result(3)])
    assert run.status == ScrapeRunStatus.success
    children = (
        db_session.query(ScrapeRun)
        .filter(ScrapeRun.organization_id.isnot(None))
        .all()
    )
    assert run.reviews_seen == sum(c.reviews_seen or 0 for c in children) == 5
    assert run.reviews_inserted == sum(c.reviews_inserted or 0 for c in children) == 5
    assert run.reviews_updated == 0


def test_zero_organizations_parent_success_zero_counters(db_session):
    run = _run_all(db_session, [_ok_result()])
    assert run.status == ScrapeRunStatus.success
    assert (run.reviews_seen, run.reviews_inserted, run.reviews_updated) == (0, 0, 0)


def test_child_exception_terminalizes_as_failed_and_parent_aggregates(db_session):
    _orgs(db_session, 2)
    run = _run_all(db_session, [RuntimeError("scraper crashed"), _captcha_result()])
    assert run.status == ScrapeRunStatus.needs_manual_action  # no success, one manual
    children = db_session.query(ScrapeRun).filter(ScrapeRun.organization_id.isnot(None)).all()
    assert {c.status for c in children} == {ScrapeRunStatus.failed, ScrapeRunStatus.needs_manual_action}
