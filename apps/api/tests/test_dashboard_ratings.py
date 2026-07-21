"""Ratings page aggregation contract (feature 014).

Covers the endpoint contract (auth, validation, empty scope) plus the four
analytical blocks: per-platform star distribution, snapshot-backed monthly
trends, weekly response percentiles, and the weekday breakdown.

Key invariants treated as contract:
  * per-star counts sum to the platform's *active* review total (SC-002)
  * removed reviews are excluded from shares but counted separately (FR-003)
  * platforms without per-review rows report None, never 0 (FR-004)
  * a snapshot gap is None, never 0 (FR-005/006)
  * weekday count 0 is real data; its avg_rating is None (FR-008)
"""

from datetime import date, datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.rating_snapshot import RatingSnapshot
from app.models.review import Review
from app.services.dashboard_service import DashboardService

NOW = datetime.now(timezone.utc)


def _org(db, **kw):
    org = Organization(
        name=kw.pop("name", "Org"),
        rating=kw.pop("rating", 4.5),
        review_count=kw.pop("review_count", 100),
        **kw,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(
    db,
    org,
    *,
    rating,
    hash_,
    first_seen=None,
    review_date=None,
    response_at=None,
    removed_at=None,
    platform=ReviewPlatform.yandex,
):
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=platform,
        rating=rating,
        review_text="text",
        content_hash=hash_,
        first_seen_at=first_seen or NOW,
        last_seen_at=first_seen or NOW,
        review_date=review_date,
        response_text="reply" if response_at else None,
        response_first_seen_at=response_at,
        removed_at=removed_at,
    )
    db.add(r)
    db.commit()
    return r


def _snapshot(db, org, *, platform, rating, review_count, captured_on):
    snap = RatingSnapshot(
        organization_id=org.id,
        platform=platform,
        rating=rating,
        review_count=review_count,
        captured_on=captured_on,
    )
    db.add(snap)
    db.commit()
    return snap


def _row(body, platform):
    return next(
        (r for r in body["platform_distribution"] if r["platform"] == platform), None
    )


def _seed_reviews(db, dates_ratings, *, org=None, platform=ReviewPlatform.yandex):
    """Seed one org (unless given) with a review per (review_date, rating) pair."""
    org = org or _org(db, name="WeekdayGrid", rating=4.0, review_count=len(dates_ratings))
    for i, (review_date, rating) in enumerate(dates_ratings):
        _review(
            db,
            org,
            rating=rating,
            hash_=f"grid-{review_date.isoformat()}-{i}",
            review_date=review_date,
            platform=platform,
        )
    return org


# --- Auth / validation (T007) ------------------------------------------------


def test_unauthenticated_returns_401(client):
    assert client.get("/api/dashboard/ratings").status_code == 401


def test_invalid_period_returns_422(admin_client):
    assert admin_client.get("/api/dashboard/ratings?period=bogus").status_code == 422


def test_invalid_platform_returns_422(admin_client):
    assert admin_client.get("/api/dashboard/ratings?platform=vk").status_code == 422


def test_custom_period_requires_both_bounds(admin_client):
    resp = admin_client.get("/api/dashboard/ratings?period=custom&date_from=2026-01-01")
    assert resp.status_code == 422


def test_custom_period_rejects_reversed_range(admin_client):
    resp = admin_client.get(
        "/api/dashboard/ratings?period=custom&date_from=2026-03-01&date_to=2026-01-01"
    )
    assert resp.status_code == 422


def test_empty_scope_returns_empty_blocks(admin_client):
    """No organizations selected -> 200 with empty blocks, never an error."""
    resp = admin_client.get("/api/dashboard/ratings?period=30d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform_distribution"] == []
    assert body["rating_trend"]["labels"] == []
    assert body["volume_trend"]["series"] == []
    assert body["response_speed"]["labels"] == []
    # weekday always has 7 slots so the UI can render a stable grid
    assert len(body["weekday"]["days"]) == 7
    assert all(d["count"] == 0 and d["avg_rating"] is None for d in body["weekday"]["days"])
    assert body["weekday"]["insight"] is None
    assert body["response_speed"]["sla_target_minutes"] > 0


# --- US1: platform distribution (T012-T014) ----------------------------------


def test_yandex_star_counts_sum_to_active_total(admin_client, db_session):
    """Per-star counts reconcile to the active total; removed rows are split out."""
    org = _org(db_session, name="D1", rating=4.2, review_count=6)
    today = NOW.date()
    # 3x 5star, 1x 4star, 1x 1star active  -> total 5
    for i, rating in enumerate([5, 5, 5, 4, 1]):
        _review(db_session, org, rating=rating, hash_=f"d1-{i}", review_date=today)
    # one removed 1star -> excluded from shares, counted in removed_count
    _review(
        db_session, org, rating=1, hash_="d1-removed", review_date=today, removed_at=NOW
    )

    body = admin_client.get("/api/dashboard/ratings?period=30d").json()
    row = _row(body, "yandex")
    assert row is not None
    assert row["total_reviews"] == 5
    assert row["removed_count"] == 1
    assert sum(s["count"] for s in row["stars"]) == row["total_reviews"]
    by_star = {s["star"]: s for s in row["stars"]}
    assert by_star[5]["count"] == 3
    assert by_star[4]["count"] == 1
    assert by_star[1]["count"] == 1
    assert by_star[3]["count"] == 0
    assert by_star[5]["share"] == 60.0
    # all five star levels are always present so the table has stable columns
    assert sorted(by_star) == [1, 2, 3, 4, 5]


def test_google_reports_none_not_zero(admin_client, db_session):
    """Google has no collector -> stars/removed are None («нет данных»).

    Yandex and 2ГИС both store individual reviews (Principle VIII), so Google is
    the only aggregate-only platform.
    """
    _org(
        db_session,
        name="D2",
        rating=4.4,
        review_count=10,
        google_rating=4.5,
        google_review_count=200,
    )

    body = admin_client.get("/api/dashboard/ratings?period=30d").json()
    row = _row(body, "google")
    assert row is not None
    assert row["avg_rating"] == 4.5
    assert row["stars"] is None
    assert row["removed_count"] is None


def test_gis2_has_per_review_distribution(admin_client, db_session):
    """2ГИС reviews are collected per-row, so it gets a real star breakdown."""
    org = _org(db_session, name="D2b", rating=4.0, review_count=2, gis2_rating=4.1)
    today = NOW.date()
    for i, rating in enumerate([5, 5, 2]):
        _review(
            db_session, org, rating=rating, hash_=f"g-{i}",
            review_date=today, platform=ReviewPlatform.gis2,
        )
    _review(
        db_session, org, rating=1, hash_="g-removed", review_date=today,
        platform=ReviewPlatform.gis2, removed_at=NOW,
    )

    body = admin_client.get("/api/dashboard/ratings?period=30d").json()
    row = _row(body, "gis2")
    assert row["stars"] is not None
    assert row["total_reviews"] == 3
    assert row["removed_count"] == 1
    assert {s["star"]: s["count"] for s in row["stars"]}[5] == 2
    assert sum(s["count"] for s in row["stars"]) == row["total_reviews"]


def test_platform_filter_narrows_distribution(admin_client, db_session):
    org = _org(
        db_session, name="D3", rating=4.0, review_count=2,
        google_rating=4.9, google_review_count=10,
    )
    _review(db_session, org, rating=5, hash_="d3-1", review_date=NOW.date())

    body = admin_client.get("/api/dashboard/ratings?period=30d&platform=yandex").json()
    assert [r["platform"] for r in body["platform_distribution"]] == ["yandex"]


def test_org_filter_narrows_distribution(admin_client, db_session):
    keep = _org(db_session, name="Keep", rating=4.0, review_count=1)
    other = _org(db_session, name="Other", rating=4.0, review_count=1)
    _review(db_session, keep, rating=5, hash_="k-1", review_date=NOW.date())
    _review(db_session, other, rating=1, hash_="o-1", review_date=NOW.date())
    _review(db_session, other, rating=1, hash_="o-2", review_date=NOW.date())

    body = admin_client.get(
        f"/api/dashboard/ratings?period=30d&org_ids={keep.id}"
    ).json()
    row = _row(body, "yandex")
    assert row["total_reviews"] == 1
    assert {s["star"]: s["count"] for s in row["stars"]}[5] == 1


def test_distribution_respects_period_window(admin_client, db_session):
    org = _org(db_session, name="D4", rating=4.0, review_count=2)
    _review(db_session, org, rating=5, hash_="p-in", review_date=NOW.date())
    _review(
        db_session, org, rating=1, hash_="p-out",
        review_date=(NOW - timedelta(days=400)).date(),
    )

    body = admin_client.get("/api/dashboard/ratings?period=30d").json()
    assert _row(body, "yandex")["total_reviews"] == 1

    body_all = admin_client.get("/api/dashboard/ratings?period=all").json()
    assert _row(body_all, "yandex")["total_reviews"] == 2


# --- US2: snapshot-backed trends (T019-T020) ---------------------------------


def _series(block, platform):
    return next((s for s in block["series"] if s["platform"] == platform), None)


def test_latest_snapshot_in_month_wins(admin_client, db_session):
    """Several snapshots in one month -> the latest captured_on supplies the point."""
    org = _org(db_session, name="S1", rating=4.0, review_count=10)
    _snapshot(
        db_session, org, platform=ReviewPlatform.yandex,
        rating=4.10, review_count=100, captured_on=date(2026, 3, 5),
    )
    _snapshot(
        db_session, org, platform=ReviewPlatform.yandex,
        rating=4.50, review_count=140, captured_on=date(2026, 3, 28),
    )

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    labels = body["rating_trend"]["labels"]
    assert "2026-03" in labels
    idx = labels.index("2026-03")
    assert _series(body["rating_trend"], "yandex")["points"][idx] == 4.5
    assert _series(body["volume_trend"], "yandex")["points"][idx] == 140


def test_month_without_snapshot_is_null_not_zero(admin_client, db_session):
    """A platform missing a month yields None (a line gap), never 0."""
    org = _org(db_session, name="S2", rating=4.0, review_count=10)
    _snapshot(
        db_session, org, platform=ReviewPlatform.yandex,
        rating=4.2, review_count=50, captured_on=date(2026, 1, 20),
    )
    _snapshot(
        db_session, org, platform=ReviewPlatform.yandex,
        rating=4.3, review_count=60, captured_on=date(2026, 2, 20),
    )
    # 2ГИС only has February -> January must be a gap
    _snapshot(
        db_session, org, platform=ReviewPlatform.gis2,
        rating=4.0, review_count=30, captured_on=date(2026, 2, 20),
    )

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    labels = body["rating_trend"]["labels"]
    assert labels == ["2026-01", "2026-02"]
    gis2 = _series(body["rating_trend"], "gis2")
    assert gis2["points"][0] is None
    assert gis2["points"][1] == 4.0
    assert _series(body["volume_trend"], "gis2")["points"][0] is None


def test_no_snapshot_history_yields_empty_trend_blocks(admin_client, db_session):
    """Organizations exist and have reviews, but no snapshots captured yet."""
    org = _org(db_session, name="S3", rating=4.0, review_count=1)
    _review(db_session, org, rating=5, hash_="s3-1", review_date=NOW.date())

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    assert body["rating_trend"]["labels"] == []
    assert body["rating_trend"]["series"] == []
    assert body["volume_trend"]["labels"] == []
    # the distribution block still works — blocks are independent
    assert _row(body, "yandex")["total_reviews"] == 1


def test_trend_aggregates_across_organizations(admin_client, db_session):
    """Network figures: volume sums, rating is review-count weighted."""
    a = _org(db_session, name="A", rating=4.0, review_count=10)
    b = _org(db_session, name="B", rating=4.0, review_count=10)
    _snapshot(
        db_session, a, platform=ReviewPlatform.yandex,
        rating=5.0, review_count=300, captured_on=date(2026, 4, 10),
    )
    _snapshot(
        db_session, b, platform=ReviewPlatform.yandex,
        rating=4.0, review_count=100, captured_on=date(2026, 4, 10),
    )

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    idx = body["rating_trend"]["labels"].index("2026-04")
    # (5.0*300 + 4.0*100) / 400 = 4.75
    assert _series(body["rating_trend"], "yandex")["points"][idx] == 4.75
    assert _series(body["volume_trend"], "yandex")["points"][idx] == 400


def test_trend_respects_platform_filter(admin_client, db_session):
    org = _org(db_session, name="S4", rating=4.0, review_count=10)
    _snapshot(
        db_session, org, platform=ReviewPlatform.yandex,
        rating=4.2, review_count=50, captured_on=date(2026, 5, 10),
    )
    _snapshot(
        db_session, org, platform=ReviewPlatform.gis2,
        rating=4.0, review_count=20, captured_on=date(2026, 5, 10),
    )

    body = admin_client.get("/api/dashboard/ratings?period=all&platform=yandex").json()
    assert [s["platform"] for s in body["rating_trend"]["series"]] == ["yandex"]


# --- US3: response speed + weekday (T026-T027) -------------------------------


def test_response_speed_buckets_by_week(admin_client, db_session):
    """Median/p95 per week, index-aligned with labels, in minutes."""
    org = _org(db_session, name="R1", rating=4.0, review_count=3)
    week_a = date(2026, 3, 2)   # Monday
    week_b = date(2026, 3, 9)   # the following Monday
    seen = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)

    # week A: delays of 30 and 90 minutes -> median 60
    _review(db_session, org, rating=5, hash_="r1-a1", review_date=week_a,
            first_seen=seen, response_at=seen + timedelta(minutes=30))
    _review(db_session, org, rating=5, hash_="r1-a2", review_date=week_a,
            first_seen=seen, response_at=seen + timedelta(minutes=90))
    # week B: a single 20-minute delay
    _review(db_session, org, rating=5, hash_="r1-b1", review_date=week_b,
            first_seen=seen, response_at=seen + timedelta(minutes=20))

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    block = body["response_speed"]
    assert len(block["labels"]) == 2
    assert len(block["median_minutes"]) == len(block["labels"])
    assert len(block["p95_minutes"]) == len(block["labels"])
    assert block["median_minutes"][0] == 60.0
    assert block["median_minutes"][1] == 20.0
    assert block["p95_minutes"][0] >= block["median_minutes"][0]
    assert block["sla_target_minutes"] > 0


def test_response_speed_ignores_unanswered(admin_client, db_session):
    org = _org(db_session, name="R2", rating=4.0, review_count=1)
    _review(db_session, org, rating=1, hash_="r2-1", review_date=date(2026, 4, 6))

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    assert body["response_speed"]["labels"] == []


def test_weekday_breakdown_counts_and_averages(admin_client, db_session):
    org = _org(db_session, name="W1", rating=4.0, review_count=4)
    monday = date(2026, 3, 2)
    friday = date(2026, 3, 6)
    assert monday.weekday() == 0 and friday.weekday() == 4

    _review(db_session, org, rating=5, hash_="w1-1", review_date=monday)
    _review(db_session, org, rating=3, hash_="w1-2", review_date=monday)
    _review(db_session, org, rating=1, hash_="w1-3", review_date=friday)
    # no review_date -> excluded from the weekday block only
    _review(db_session, org, rating=2, hash_="w1-4", review_date=None)

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    days = body["weekday"]["days"]
    assert len(days) == 7
    assert [d["weekday"] for d in days] == list(range(7))
    assert days[0]["label"] == "Пн" and days[6]["label"] == "Вс"

    assert days[0]["count"] == 2
    assert days[0]["avg_rating"] == 4.0
    assert days[4]["count"] == 1
    assert days[4]["avg_rating"] == 1.0

    # A weekday with no reviews: 0 is real data, but there is no average.
    assert days[2]["count"] == 0
    assert days[2]["avg_rating"] is None

    insight = body["weekday"]["insight"]
    assert insight is not None
    assert "пятница" in insight.lower()
    assert "понедельник" in insight.lower()


def test_weekday_insight_absent_without_enough_data(admin_client, db_session):
    org = _org(db_session, name="W2", rating=4.0, review_count=1)
    _review(db_session, org, rating=5, hash_="w2-1", review_date=date(2026, 3, 2))

    body = admin_client.get("/api/dashboard/ratings?period=all").json()
    # only one weekday carries data -> no best/worst comparison to make
    assert body["weekday"]["insight"] is None


def test_weekday_respects_org_filter(admin_client, db_session):
    keep = _org(db_session, name="WK", rating=4.0, review_count=1)
    other = _org(db_session, name="WO", rating=4.0, review_count=1)
    monday = date(2026, 3, 2)
    _review(db_session, keep, rating=5, hash_="wk-1", review_date=monday)
    _review(db_session, other, rating=1, hash_="wo-1", review_date=monday)

    body = admin_client.get(
        f"/api/dashboard/ratings?period=all&org_ids={keep.id}"
    ).json()
    days = body["weekday"]["days"]
    assert days[0]["count"] == 1
    assert days[0]["avg_rating"] == 5.0


# --- Weekday grid (custom range only) -----------------------------------------


def test_weekday_grid_present_only_for_custom_range(db_session):
    # Seed a handful of yandex reviews across two dates/weekdays.
    _seed_reviews(db_session, dates_ratings=[
        (date(2026, 6, 1), 5),   # Monday
        (date(2026, 6, 2), 3),   # Tuesday
        (date(2026, 6, 8), 4),   # Monday
    ])
    svc = DashboardService(db_session)

    preset = svc.ratings(period="30d", platform="all")
    assert preset["weekday"].get("grid") is None  # bars mode only

    custom = svc.ratings(
        period="custom", platform="all",
        date_from=date(2026, 6, 1), date_to=date(2026, 6, 14),
    )
    grid = custom["weekday"]["grid"]
    assert grid is not None
    assert len(grid["rows"]) == 7
    # 14-day range -> daily buckets
    assert len(grid["columns"]) == 14
    for row in grid["rows"]:
        assert len(row["cells"]) == len(grid["columns"])


def test_weekday_grid_granularity_thresholds(db_session):
    _seed_reviews(db_session, dates_ratings=[(date(2026, 1, 5), 5)])
    svc = DashboardService(db_session)

    day = svc.ratings(period="custom", platform="all",
                      date_from=date(2026, 1, 1), date_to=date(2026, 1, 14))
    assert len(day["weekday"]["grid"]["columns"]) == 14  # daily

    week = svc.ratings(period="custom", platform="all",
                       date_from=date(2026, 1, 1), date_to=date(2026, 3, 1))
    # ~60 days -> weekly buckets, far fewer than 60 columns
    assert 0 < len(week["weekday"]["grid"]["columns"]) <= 10

    month = svc.ratings(period="custom", platform="all",
                        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
    # 365 days -> monthly buckets
    assert len(month["weekday"]["grid"]["columns"]) == 12


def test_weekday_grid_empty_cell_avg_is_null(db_session):
    # Single review on Monday 2026-06-01; every other weekday/period empty.
    _seed_reviews(db_session, dates_ratings=[(date(2026, 6, 1), 5)])
    svc = DashboardService(db_session)
    grid = svc.ratings(period="custom", platform="all",
                       date_from=date(2026, 6, 1), date_to=date(2026, 6, 14))["weekday"]["grid"]
    # Find a cell with count 0 -> avg_rating must be None, never 0.
    empties = [c for row in grid["rows"] for c in row["cells"] if c["count"] == 0]
    assert empties, "expected empty cells in a sparse grid"
    assert all(c["avg_rating"] is None for c in empties)


def test_weekday_grid_weekly_buckets_match_between_python_and_sql(db_session):
    """Regression: SQLite week-bucket keys built in Python must match the SQL
    GROUP BY key produced by ``_week_key_expr`` — otherwise the grid silently
    drops every review into "no matching column" and every cell reads empty."""
    _seed_reviews(db_session, dates_ratings=[
        (date(2026, 1, 5), 5),
        (date(2026, 1, 20), 3),
        (date(2026, 2, 10), 4),
    ])
    svc = DashboardService(db_session)
    grid = svc.ratings(period="custom", platform="all",
                       date_from=date(2026, 1, 1), date_to=date(2026, 3, 1))["weekday"]["grid"]
    total = sum(c["count"] for row in grid["rows"] for c in row["cells"])
    assert total == 3, (
        "weekly bucket keys from Python and SQL did not line up; "
        f"expected 3 seeded reviews to land in cells, got {total}"
    )


# --- Serialization contract (schema validation) -------------------------------


def test_ratings_response_serializes_weekday_grid(db_session):
    """WeekdayGrid and WeekdayBlock.grid validate correctly under Pydantic."""
    from app.schemas.dashboard import DashboardRatings

    _seed_reviews(db_session, dates_ratings=[(date(2026, 6, 1), 5)])
    payload = DashboardService(db_session).ratings(
        period="custom", platform="all",
        date_from=date(2026, 6, 1), date_to=date(2026, 6, 14),
    )
    model = DashboardRatings.model_validate(payload)
    assert model.weekday.grid is not None
    assert len(model.weekday.grid.rows) == 7
    assert model.weekday.grid.columns[0].key
    assert len(model.weekday.grid.rows[0].cells) == len(model.weekday.grid.columns)
