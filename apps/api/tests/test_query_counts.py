"""Feature 010 / US5: bounded query counts — no N+1 in upsert, overview, companies."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.models.company import Company
from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.scraper.types import ParsedReview
from app.services.dashboard_service import DashboardService
from app.services.review_service import ReviewService


@pytest.fixture()
def query_counter(db_session):
    """Counts SELECT statements issued on the test engine."""
    engine = db_session.get_bind()
    counter = {"selects": 0, "total": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        counter["total"] += 1
        if statement.lstrip().upper().startswith("SELECT"):
            counter["selects"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    yield counter
    event.remove(engine, "before_cursor_execute", _count)


def _parsed(i: int) -> ParsedReview:
    return ParsedReview(
        author_name=f"Author {i}",
        rating=(i % 5) + 1,
        review_text=f"Review body {i}",
        review_date_text=f"{(i % 27) + 1} июня",
        review_date=date(2026, 6, (i % 27) + 1),
    )


def _seed_orgs(db, n):
    orgs = [
        Organization(yandex_url=f"https://yandex.ru/maps/org/o{i}/{i}/", rating=4.5, review_count=10)
        for i in range(n)
    ]
    db.add_all(orgs)
    db.commit()
    return orgs


def test_upsert_reviews_constant_select_count(db_session, query_counter):
    org = _seed_orgs(db_session, 1)[0]
    service = ReviewService(db_session)

    query_counter["selects"] = 0
    service.upsert_reviews(org.id, [_parsed(i) for i in range(50)], ScrapeMode.public)

    # One batch preload SELECT; a couple of bookkeeping SELECTs are tolerated,
    # but never one per review.
    assert query_counter["selects"] <= 3, f"expected O(1) SELECTs, got {query_counter['selects']}"


def test_overview_query_count_does_not_scale_with_orgs(db_session, query_counter):
    def measure(n_orgs: int) -> int:
        db_session.query(Organization).delete()
        db_session.commit()
        orgs = _seed_orgs(db_session, n_orgs)
        service = ReviewService(db_session)
        dash = DashboardService(db_session)
        now = datetime.now(timezone.utc)
        for i, org in enumerate(orgs):
            service.upsert_reviews(org.id, [_parsed(i * 10 + j) for j in range(3)], ScrapeMode.public)
            dash.capture_snapshot(org.id, ReviewPlatform.yandex, now=now - timedelta(days=5))

        query_counter["selects"] = 0
        dash.overview(period="30d", platform="all")
        return query_counter["selects"]

    q2, q5 = measure(2), measure(5)
    assert q5 == q2, f"overview SELECT count scales with org count: {q2} -> {q5}"


def test_overview_query_count_does_not_scale_with_reviews(db_session, query_counter):
    """Feature 012: overview must aggregate in SQL — same SELECT count at any review volume."""
    orgs = _seed_orgs(db_session, 2)
    service = ReviewService(db_session)
    dash = DashboardService(db_session)

    def measure(extra_reviews: int) -> int:
        for org in orgs:
            service.upsert_reviews(
                org.id, [_parsed(i) for i in range(extra_reviews)], ScrapeMode.public
            )
        query_counter["selects"] = 0
        dash.overview(period="30d", platform="all")
        return query_counter["selects"]

    q_small, q_large = measure(20), measure(60)
    assert q_large == q_small, f"overview SELECT count scales with review count: {q_small} -> {q_large}"


def test_overview_platform_filter_no_extra_scan(db_session, query_counter):
    """Feature 012 / US2: a platform-filtered overview issues no more SELECTs than unfiltered."""
    orgs = _seed_orgs(db_session, 3)
    service = ReviewService(db_session)
    dash = DashboardService(db_session)
    for org in orgs:
        service.upsert_reviews(org.id, [_parsed(i) for i in range(5)], ScrapeMode.public)

    query_counter["selects"] = 0
    dash.overview(period="30d", platform="all")
    q_all = query_counter["selects"]

    query_counter["selects"] = 0
    dash.overview(period="30d", platform="yandex")
    q_filtered = query_counter["selects"]

    assert q_filtered <= q_all, f"platform filter added SELECTs: {q_all} -> {q_filtered}"


def test_overview_empty_selection_short_circuits(db_session, query_counter):
    """Feature 012 / US2: no matching orgs -> empty payload, no review queries."""
    from uuid import uuid4

    dash = DashboardService(db_session)
    query_counter["selects"] = 0
    payload = dash.overview(period="30d", platform="all", org_ids=[uuid4()])
    assert payload["kpi_hero"]["total_reviews"] == 0
    # only the organization-selection SELECT is allowed
    assert query_counter["selects"] <= 1, f"empty selection issued {query_counter['selects']} SELECTs"


def test_companies_list_bounded_queries(admin_client, db_session, query_counter):
    companies = [Company(name=f"Co {i}", is_active=True) for i in range(10)]
    db_session.add_all(companies)
    db_session.commit()
    for i, c in enumerate(companies):
        db_session.add(Organization(yandex_url=f"https://yandex.ru/maps/org/c{i}/{i}/", company_id=c.id))
    db_session.commit()

    query_counter["selects"] = 0
    resp = admin_client.get("/api/companies")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 10
    assert all(item["branch_count"] == 1 for item in items)
    # session/user lookup + companies + grouped counts — never one COUNT per company
    assert query_counter["selects"] <= 5, f"companies list issued {query_counter['selects']} SELECTs"


# --- Feature 014: ratings page ------------------------------------------------


def test_ratings_query_count_does_not_scale_with_orgs(db_session, query_counter):
    def measure(n_orgs: int) -> int:
        db_session.query(Organization).delete()
        db_session.commit()
        orgs = _seed_orgs(db_session, n_orgs)
        service = ReviewService(db_session)
        dash = DashboardService(db_session)
        now = datetime.now(timezone.utc)
        for i, org in enumerate(orgs):
            service.upsert_reviews(org.id, [_parsed(i * 10 + j) for j in range(3)], ScrapeMode.public)
            dash.capture_snapshot(org.id, ReviewPlatform.yandex, now=now - timedelta(days=5))

        query_counter["selects"] = 0
        dash.ratings(period="30d", platform="all")
        return query_counter["selects"]

    q2, q5 = measure(2), measure(5)
    assert q5 == q2, f"ratings SELECT count scales with org count: {q2} -> {q5}"


def test_ratings_query_count_does_not_scale_with_reviews(db_session, query_counter):
    """Every block aggregates in SQL — same SELECT count at any review volume."""
    orgs = _seed_orgs(db_session, 2)
    service = ReviewService(db_session)
    dash = DashboardService(db_session)

    def measure(extra_reviews: int) -> int:
        for org in orgs:
            service.upsert_reviews(
                org.id, [_parsed(i) for i in range(extra_reviews)], ScrapeMode.public
            )
        query_counter["selects"] = 0
        dash.ratings(period="30d", platform="all")
        return query_counter["selects"]

    q_small, q_large = measure(20), measure(60)
    assert q_large == q_small, f"ratings SELECT count scales with review count: {q_small} -> {q_large}"
