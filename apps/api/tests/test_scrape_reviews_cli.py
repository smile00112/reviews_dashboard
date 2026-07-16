"""Argument handling for the review-collection CLI (scripts/scrape_reviews.py).

Offline: only parsing/validation and the platform→mode resolution, no DB or network.
"""

import math

import pytest

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.models.scrape_run import ScrapeRun
from scripts.scrape_metrics import RunLogger
from scripts.scrape_reviews import build_parser, resolve_mode, resolve_overrides, run, validate_args

ORG_ID = "007cab4a-d857-47af-997c-61b7d8e0523e"


def _parse(argv):
    return build_parser().parse_args(argv)


def test_org_id_and_all_together_are_rejected():
    args = _parse(["--org-id", ORG_ID, "--all"])
    with pytest.raises(SystemExit):
        validate_args(args)


def test_neither_org_id_nor_all_is_rejected():
    args = _parse([])
    with pytest.raises(SystemExit):
        validate_args(args)


def test_org_id_alone_is_accepted():
    validate_args(_parse(["--org-id", ORG_ID]))


def test_all_alone_is_accepted():
    validate_args(_parse(["--all"]))


def test_platform_yandex_defaults_to_public_http():
    # public (Playwright) cannot authenticate against the SOCKS5 proxy pool, so the
    # working default for Yandex is the browserless mode.
    assert resolve_mode(_parse(["--all", "--platform", "yandex"])) == ScrapeMode.public_http


def test_platform_2gis_defaults_to_twogis_api():
    assert resolve_mode(_parse(["--all", "--platform", "2gis"])) == ScrapeMode.twogis_api


def test_explicit_mode_overrides_the_platform_default():
    args = _parse(["--all", "--platform", "yandex", "--mode", "scrapeops"])
    assert resolve_mode(args) == ScrapeMode.scrapeops


def test_mode_from_another_platform_is_rejected():
    args = _parse(["--all", "--platform", "2gis", "--mode", "public_http"])
    with pytest.raises(SystemExit):
        validate_args(args)


def test_twogis_mode_under_yandex_platform_is_rejected():
    args = _parse(["--all", "--platform", "yandex", "--mode", "twogis_api"])
    with pytest.raises(SystemExit):
        validate_args(args)


def test_all_reviews_with_a_scroll_mode_is_rejected():
    # public/operator_auth scroll instead of paginating and have no limit knob;
    # accepting --all-reviews there would silently collect the scroll-capped set.
    args = _parse(["--all", "--platform", "yandex", "--mode", "public", "--all-reviews"])
    with pytest.raises(SystemExit):
        validate_args(args)


def test_all_reviews_maps_to_infinite_limit_and_page_ceiling():
    args = _parse(["--all", "--all-reviews"])
    assert resolve_overrides(args) == {"limit": math.inf, "max_pages": 100}


def test_without_all_reviews_no_overrides_are_sent():
    # Omitted → scrapers fall back to their settings values (150/5).
    assert resolve_overrides(_parse(["--all"])) == {}


def test_dry_run_writes_nothing_and_scrapes_nothing(db_session):
    """--dry-run must be a plan preview.

    ScrapeService commits internally (_persist_scrape_result), so a
    scrape-then-rollback dry run is impossible here: the writes are already
    committed by the time the CLI could roll back. The flag therefore must not
    scrape at all — an earlier version did, and wrote 150 reviews on a --dry-run.
    """
    org = Organization(
        name="Тест",
        yandex_url="https://yandex.ru/maps/org/test/123/reviews/",
        preferred_scrape_mode=ScrapeMode.public_http,
    )
    db_session.add(org)
    db_session.commit()

    def explode(*a, **kw):
        raise AssertionError("--dry-run must not invoke a scraper")

    import scripts.scrape_reviews as module

    original = module.ScrapeService.execute_run
    module.ScrapeService.execute_run = explode
    try:
        summary = run(db_session, _parse(["--all", "--dry-run"]), RunLogger(None))
    finally:
        module.ScrapeService.execute_run = original

    assert summary.planned == 1
    assert db_session.query(Review).count() == 0
    assert db_session.query(ScrapeRun).count() == 0
