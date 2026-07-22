"""Network overview aggregation contract (feature 009, US1 headline KPIs).

Verifies header counts, hero KPIs, and strip KPIs reconcile to seeded reviews,
plus auth/validation and the empty-network zeroed payload.
"""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ReviewStatus
from app.models.organization import Organization
from app.models.review import Review
from app.models.enums import ScrapeMode

NOW = datetime.now(timezone.utc)


def _org(db, **kw):
    org = Organization(name=kw.pop("name", "Org"), rating=kw.pop("rating", 4.5), review_count=kw.pop("review_count", 100), **kw)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, rating, first_seen, response_at=None, sentiment=None, hash_,
            review_date=None, problems=None, status=None, platform=ReviewPlatform.yandex):
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=platform,
        rating=rating,
        review_text="text",
        content_hash=hash_,
        first_seen_at=first_seen,
        last_seen_at=first_seen,
        response_text="reply" if response_at else None,
        response_first_seen_at=response_at,
        sentiment=sentiment,
        review_date=review_date,
        problems=problems,
        status=status,
    )
    db.add(r)
    db.commit()
    return r


def _seed_rules(db):
    from app.services.attention_rule_service import AttentionRuleService
    AttentionRuleService(db).seed_defaults()


def _seed_arm_sweep(db, *, window_days=10, period_days=60):
    """Feature 015: seed the default rules, open their window over the seeded
    reviews, and run one sweep so the block has latched snapshots to read."""
    from app.services.attention_evaluator import AttentionEvaluator
    from app.services.attention_rule_service import AttentionRuleService

    svc = AttentionRuleService(db)
    svc.seed_defaults()
    for rule in svc.list_rules():
        rule.window_started_at = NOW - timedelta(days=window_days)
        rule.period_days = period_days
        rule.latched_at = None
    db.commit()
    AttentionEvaluator(db).sweep(now=NOW)


# --- Auth / validation -------------------------------------------------------

def test_unauthenticated_returns_401(client):
    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 401


def test_invalid_period_returns_422(admin_client):
    resp = admin_client.get("/api/dashboard/overview?period=bogus")
    assert resp.status_code == 422


def test_invalid_platform_returns_422(admin_client):
    resp = admin_client.get("/api/dashboard/overview?platform=vk")
    assert resp.status_code == 422


def test_empty_network_zeroed_payload(admin_client):
    resp = admin_client.get("/api/dashboard/overview?period=30d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kpi_hero"]["total_reviews"] == 0
    assert body["kpi_hero"]["network_avg_rating"] is None
    assert body["header"]["new_in_period"] == 0
    assert body["platform_breakdown"] == []
    assert body["attention"] == []


# --- US1 headline KPIs -------------------------------------------------------

def test_headline_kpis_reconcile(admin_client, db_session):
    org = _org(db_session, rating=4.5, review_count=100)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(hours=1),
            response_at=NOW - timedelta(hours=1) + timedelta(minutes=10), sentiment="positive", hash_="h1")
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(hours=1),
            sentiment="negative", hash_="h2")  # fresh negative, unanswered
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(hours=48),
            sentiment="positive", hash_="h3")  # overdue unanswered
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=100),
            response_at=NOW - timedelta(days=100), sentiment="positive", hash_="h4")  # outside 30d

    body = admin_client.get("/api/dashboard/overview?period=30d").json()

    header = body["header"]
    assert header["new_in_period"] == 3           # h1,h2,h3 (h4 outside window)
    assert header["unanswered_over_24h"] == 1     # h3 only
    assert header["fresh_negatives_2h"] == 1      # h2

    hero = body["kpi_hero"]
    assert hero["total_reviews"] == 4
    assert hero["new_in_period"] == 3
    assert hero["network_avg_rating"] == 4.5
    assert hero["unanswered_total"] == 2          # h2,h3
    assert hero["overdue_24h"] == 1

    strip = body["kpi_strip"]
    assert strip["response_avg_min"] == 10        # only h1 has a response in period
    assert strip["response_approximate"] is True
    assert strip["sla_percent"] == 100.0
    assert strip["positivity_percent"] == 66.7    # 2 positive / 3 analyzed in period
    assert strip["reputation_index"] == 0.0       # share5 33.3 - share1-3 33.3


def test_period_counts_use_publication_date_not_first_seen(admin_client, db_session):
    """A first bulk import stamps every row with today's ``first_seen_at``; the
    period counters must follow ``review_date`` so the backlog isn't reported as
    new. Rows without a ``review_date`` still fall back to ``first_seen_at``."""
    org = _org(db_session)
    today = NOW.date()
    # Imported today, but published long ago -> backlog, not new.
    for i in range(3):
        _review(db_session, org, rating=5, first_seen=NOW - timedelta(minutes=5),
                review_date=today - timedelta(days=200), hash_=f"old{i}")
    # Imported today and published today -> genuinely new.
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(minutes=5),
            review_date=today, hash_="new1")
    # No publication date at all -> falls back to the sighting day.
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(minutes=5), hash_="nodate")

    hero = admin_client.get("/api/dashboard/overview?period=day").json()["kpi_hero"]
    assert hero["total_reviews"] == 5
    assert hero["new_in_period"] == 2   # new1 + nodate
    assert hero["new_today"] == 2


# --- Feature 014: period-over-period hero deltas -----------------------------

def test_hero_deltas_compare_with_previous_equal_window(admin_client, db_session):
    """"Новых за период" / "Без ответа" deltas must follow the selected period,
    not a fixed 24h window: week vs the 7 days right before it."""
    org = _org(db_session)
    today = NOW.date()
    # Current week: 3 reviews, 2 of them unanswered.
    for i in range(2):
        _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=2),
                review_date=today - timedelta(days=2), hash_=f"cur{i}")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=2),
            response_at=NOW - timedelta(days=2), review_date=today - timedelta(days=2), hash_="cur_ans")
    # Previous week (days 8..14 back): 1 review, unanswered.
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(days=10),
            review_date=today - timedelta(days=10), hash_="prev1")

    hero = admin_client.get("/api/dashboard/overview?period=week").json()["kpi_hero"]
    assert hero["new_in_period"] == 3
    assert hero["new_in_period_delta"] == 2        # 3 this week vs 1 the week before
    assert hero["unanswered_total"] == 2
    assert hero["unanswered_delta_period"] == 1    # 2 vs 1
    assert hero["period_days"] == 7


def test_hero_deltas_absent_for_all_time_period(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=2), hash_="a1")

    hero = admin_client.get("/api/dashboard/overview?period=all").json()["kpi_hero"]
    assert hero["new_in_period_delta"] is None
    assert hero["unanswered_delta_period"] is None


def test_rating_delta_uses_snapshot_taken_before_period_start(admin_client, db_session):
    """Baseline is the last snapshot at/before the period start — a snapshot taken
    inside the period must not become the base while an older one exists."""
    from app.models.enums import ReviewPlatform as P
    from app.services.dashboard_service import DashboardService

    org = _org(db_session, rating=4.0)
    dash = DashboardService(db_session)
    org.rating = 3.8
    dash.capture_snapshot(org.id, P.yandex, now=NOW - timedelta(days=20))  # before the week
    org.rating = 4.0
    dash.capture_snapshot(org.id, P.yandex, now=NOW - timedelta(days=2))   # inside the week
    db_session.commit()

    hero = admin_client.get("/api/dashboard/overview?period=week&platform=yandex").json()["kpi_hero"]
    assert hero["network_avg_rating_delta"] == 0.2   # 4.0 now vs 3.8 at period start


def test_strip_deltas_compare_with_previous_equal_window(admin_client, db_session):
    """KPI-strip cards (ср. время ответа / SLA / позитивность / индекс репутации)
    carry a period-over-period delta, same window logic as the hero cards."""
    org = _org(db_session)
    today = NOW.date()
    cur = NOW - timedelta(days=2)
    cur_day = today - timedelta(days=2)
    # Current week: answered pos-5 (+10 min) and answered neg-1 (+30 min).
    _review(db_session, org, rating=5, first_seen=cur, response_at=cur + timedelta(minutes=10),
            sentiment="positive", review_date=cur_day, hash_="cA")
    _review(db_session, org, rating=1, first_seen=cur, response_at=cur + timedelta(minutes=30),
            sentiment="negative", review_date=cur_day, hash_="cB")
    # Previous week: one answered pos-5 (+60 min).
    prev = NOW - timedelta(days=10)
    _review(db_session, org, rating=5, first_seen=prev, response_at=prev + timedelta(minutes=60),
            sentiment="positive", review_date=today - timedelta(days=10), hash_="pA")

    strip = admin_client.get("/api/dashboard/overview?period=week").json()["kpi_strip"]
    assert strip["response_avg_min"] == 20            # (10+30)/2
    assert strip["response_avg_min_delta"] == -40     # 20 now vs 60 before (faster = good)
    assert strip["positivity_percent"] == 50.0        # 1 of 2 analyzed
    assert strip["positivity_percent_delta"] == -50.0  # 50 vs 100 before
    assert strip["reputation_index"] == 0.0           # 50% five-star − 50% ≤3-star
    assert strip["reputation_index_delta"] == -100.0  # 0 vs 100 before


def test_strip_deltas_absent_for_all_time_period(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=2),
            response_at=NOW - timedelta(days=2) + timedelta(minutes=5),
            sentiment="positive", hash_="s1")

    strip = admin_client.get("/api/dashboard/overview?period=all").json()["kpi_strip"]
    assert strip["response_avg_min_delta"] is None
    assert strip["sla_percent_delta"] is None
    assert strip["positivity_percent_delta"] is None
    assert strip["reputation_index_delta"] is None


# --- US2 distribution / sentiment / platform --------------------------------

def test_rating_distribution(admin_client, db_session):
    org = _org(db_session)
    for i, rating in enumerate([5, 5, 4, 3, 1]):
        _review(db_session, org, rating=rating, first_seen=NOW - timedelta(hours=1), hash_=f"d{i}")

    dist = admin_client.get("/api/dashboard/overview?period=30d").json()["rating_distribution"]
    assert dist["total"] == 5
    by_star = {b["star"]: b["count"] for b in dist["bars"]}
    assert by_star == {5: 2, 4: 1, 3: 1, 2: 0, 1: 1}
    assert dist["share_4_5"] == 60.0
    assert dist["share_1_3"] == 40.0


def test_sentiment_counts(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(hours=1), sentiment="positive", hash_="s1")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(hours=1), sentiment="positive", hash_="s2")
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(hours=1), sentiment="negative", hash_="s3")

    s = admin_client.get("/api/dashboard/overview?period=30d").json()["sentiment"]
    assert s["positive"] == 2
    assert s["negative"] == 1
    assert s["analyzed_total"] == 3
    assert s["positive_percent"] == 66.7


def test_platform_breakdown_from_org_columns(admin_client, db_session):
    _org(db_session, name="Multi", rating=4.5, review_count=100,
         gis2_rating=4.1, gis2_review_count=50, google_rating=4.6, google_review_count=200)
    body = admin_client.get("/api/dashboard/overview?period=all").json()
    counts = {p["platform"]: p["review_count"] for p in body["platform_breakdown"]}
    assert counts == {"yandex": 100, "gis2": 50, "google": 200}


def test_platform_cards_google_has_no_per_review_data(admin_client, db_session):
    org = _org(db_session, rating=4.5, review_count=10, google_rating=4.6, google_review_count=200)
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(hours=1), hash_="y1")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(hours=1), hash_="y2")

    cards = {c["platform"]: c for c in admin_client.get("/api/dashboard/overview?period=30d").json()["platform_cards"]}
    assert cards["yandex"]["negativity_percent"] == 50.0
    assert cards["yandex"]["weighted_rating"] == 4.5
    assert cards["google"]["negativity_percent"] is None
    assert cards["google"]["response_speed_hours"] is None
    assert cards["google"]["weighted_rating"] == 4.6


# --- US3 attention feed ------------------------------------------------------

def test_attention_urgent_and_escalated(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(hours=48), hash_="over")  # overdue unanswered
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(hours=1), hash_="neg")    # fresh negative
    _review(db_session, org, rating=2, first_seen=NOW - timedelta(days=3),
            status=ReviewStatus.escalated, hash_="esc")
    _seed_arm_sweep(db_session, window_days=5, period_days=30)

    items = admin_client.get("/api/dashboard/overview?period=30d").json()["attention"]
    types = [i["type"] for i in items]
    assert "unanswered_overdue" in types
    assert "fresh_negative" in types
    assert "escalated" in types
    # urgent items ranked before warn
    severities = [i["severity"] for i in items]
    assert severities == sorted(severities, key=lambda s: {"urgent": 0, "warn": 1}.get(s, 9))


def test_attention_aspect_spike(admin_client, db_session):
    org = _org(db_session)
    today = NOW.date()
    # 4 recent mentions of "опоздание", 1 in the prior window -> spike
    for i in range(4):
        _review(db_session, org, rating=3, first_seen=NOW - timedelta(days=1),
                review_date=today - timedelta(days=2), problems=[{"category": "опоздание"}], hash_=f"r{i}")
    _review(db_session, org, rating=3, first_seen=NOW - timedelta(days=10),
            review_date=today - timedelta(days=10), problems=[{"category": "опоздание"}], hash_="p0")
    # window [NOW-3d, NOW] recent; [NOW-10d, NOW-3d] previous.
    _seed_arm_sweep(db_session, window_days=3, period_days=7)

    items = admin_client.get("/api/dashboard/overview?period=all").json()["attention"]
    spikes = [i for i in items if i["type"] == "aspect_spike"]
    assert spikes and "опоздание" in spikes[0]["title"]


def test_attention_rating_drop_needs_history(admin_client, db_session):
    from app.models.enums import ReviewPlatform
    from app.services.dashboard_service import DashboardService

    from app.services.attention_evaluator import AttentionEvaluator

    org = _org(db_session, rating=4.2)
    # Arm the rules with an open window, then sweep: no snapshot yet -> no drop.
    _seed_arm_sweep(db_session, window_days=15, period_days=60)
    body = admin_client.get("/api/dashboard/overview?period=30d").json()
    assert not any(i["type"] == "rating_drop" for i in body["attention"])

    # Snapshot 29d ago at 4.5, current 4.2 -> delta -0.3 -> drop appears after re-sweep.
    old = datetime(NOW.year, NOW.month, NOW.day, tzinfo=timezone.utc) - timedelta(days=29)
    org.rating = 4.5
    db_session.commit()
    DashboardService(db_session).capture_snapshot(org.id, ReviewPlatform.yandex, now=old)
    org.rating = 4.2
    db_session.commit()

    AttentionEvaluator(db_session).sweep(now=NOW)  # rule still armed -> re-evaluates
    body = admin_client.get("/api/dashboard/overview?period=30d").json()
    drops = [i for i in body["attention"] if i["type"] == "rating_drop"]
    assert drops and drops[0]["value"] <= -0.2


# --- US4 worst locations / trending aspects ---------------------------------

def test_worst_locations_ordered_rating_asc(admin_client, db_session):
    a = _org(db_session, name="Good", rating=4.8)
    b = _org(db_session, name="Bad", rating=3.8)
    c = _org(db_session, name="Mid", rating=4.2)
    _review(db_session, b, rating=1, first_seen=NOW - timedelta(hours=1), hash_="b1")  # unanswered

    worst = admin_client.get("/api/dashboard/overview?period=all").json()["worst_locations"]
    names = [w["name"] for w in worst]
    assert names[:3] == ["Bad", "Mid", "Good"]
    bad = next(w for w in worst if w["name"] == "Bad")
    assert bad["rating"] == 3.8
    assert bad["unanswered_count"] == 1


def test_trending_aspects(admin_client, db_session):
    org = _org(db_session)
    today = NOW.date()
    for i in range(3):
        _review(db_session, org, rating=2, first_seen=NOW - timedelta(days=1),
                review_date=today - timedelta(days=2), problems=[{"category": "курьер"}],
                sentiment="negative", hash_=f"c{i}")
    _review(db_session, org, rating=2, first_seen=NOW - timedelta(days=10),
            review_date=today - timedelta(days=10), problems=[{"category": "курьер"}],
            sentiment="negative", hash_="cp")

    aspects = admin_client.get("/api/dashboard/overview?period=all").json()["trending_aspects"]
    top = aspects[0]
    assert top["category"] == "курьер"
    assert top["mentions"] == 3
    assert top["change_percent"] == 200  # (3-1)/1*100
    assert top["sentiment"]["neg"] == 3


def test_org_filter_narrows(admin_client, db_session):
    a = _org(db_session, name="A", rating=4.0)
    b = _org(db_session, name="B", rating=3.0)
    _review(db_session, a, rating=5, first_seen=NOW - timedelta(hours=1), sentiment="positive", hash_="a1")
    _review(db_session, b, rating=1, first_seen=NOW - timedelta(hours=1), sentiment="negative", hash_="b1")

    body = admin_client.get(f"/api/dashboard/overview?org_ids={a.id}").json()
    assert body["kpi_hero"]["total_reviews"] == 1
    assert body["kpi_hero"]["network_avg_rating"] == 4.0


# --- US5 filters -------------------------------------------------------------

def test_platform_filter_narrows(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(hours=1), hash_="y", platform=ReviewPlatform.yandex)
    _review(db_session, org, rating=3, first_seen=NOW - timedelta(hours=1), hash_="g", platform=ReviewPlatform.gis2)

    assert admin_client.get("/api/dashboard/overview?period=all").json()["kpi_hero"]["total_reviews"] == 2
    assert admin_client.get("/api/dashboard/overview?platform=yandex&period=all").json()["kpi_hero"]["total_reviews"] == 1
    assert admin_client.get("/api/dashboard/overview?platform=gis2&period=all").json()["kpi_hero"]["total_reviews"] == 1


def test_company_scopes(admin_client, db_session):
    from app.models.company import Company

    comp = Company(name="Chain")
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)

    inside = _org(db_session, name="Inside", rating=4.0, company_id=comp.id)
    _org(db_session, name="Outside", rating=3.0)
    _review(db_session, inside, rating=5, first_seen=NOW - timedelta(hours=1), hash_="in")

    body = admin_client.get(f"/api/dashboard/overview?company_id={comp.id}&period=all").json()
    assert body["kpi_hero"]["total_reviews"] == 1
    assert body["kpi_hero"]["network_avg_rating"] == 4.0


# --- Feature 013: custom date range -----------------------------------------

def _d(days_ago: int):
    """Publication date ``days_ago`` days before today (UTC)."""
    return (NOW - timedelta(days=days_ago)).date()


def _range_url(frm, to, **extra):
    qs = "".join(f"&{k}={v}" for k, v in extra.items())
    return f"/api/dashboard/overview?period=custom&date_from={frm}&date_to={to}{qs}"


def test_custom_range_bounds_are_inclusive(admin_client, db_session):
    org = _org(db_session)
    # published exactly on the lower bound / upper bound -> inside; neighbours -> outside
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=11), review_date=_d(11), hash_="before")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=10), review_date=_d(10), hash_="lower")
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(days=7), review_date=_d(7), hash_="middle")
    _review(db_session, org, rating=4, first_seen=NOW - timedelta(days=5), review_date=_d(5), hash_="upper")
    _review(db_session, org, rating=3, first_seen=NOW - timedelta(days=4), review_date=_d(4), hash_="after")

    body = admin_client.get(_range_url(_d(10), _d(5))).json()

    assert body["period"] == "custom"
    assert body["header"]["new_in_period"] == 3      # lower, middle, upper
    assert body["kpi_hero"]["new_in_period"] == 3
    assert body["kpi_hero"]["total_reviews"] == 5    # all-time total is range-independent


def test_custom_range_single_day(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=3), review_date=_d(3), hash_="day")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=2), review_date=_d(2), hash_="next")

    body = admin_client.get(_range_url(_d(3), _d(3))).json()
    assert body["header"]["new_in_period"] == 1
    assert body["kpi_hero"]["avg_per_day"] == 1.0    # one inclusive day in the range


def test_custom_range_with_no_reviews_is_zeroed(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=1), review_date=_d(1), hash_="recent")

    body = admin_client.get(_range_url(_d(300), _d(290))).json()
    assert body["header"]["new_in_period"] == 0
    assert body["kpi_hero"]["new_in_period"] == 0
    assert body["kpi_hero"]["total_reviews"] == 1


def test_custom_range_requires_both_dates(admin_client):
    assert admin_client.get("/api/dashboard/overview?period=custom").status_code == 422
    assert admin_client.get(f"/api/dashboard/overview?period=custom&date_from={_d(5)}").status_code == 422
    assert admin_client.get(f"/api/dashboard/overview?period=custom&date_to={_d(5)}").status_code == 422


def test_custom_range_rejects_inverted_bounds(admin_client):
    assert admin_client.get(_range_url(_d(1), _d(10))).status_code == 422


def test_dates_ignored_for_preset_period(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=1), review_date=_d(1), hash_="recent")

    url = f"/api/dashboard/overview?period=30d&date_from={_d(300)}&date_to={_d(290)}"
    body = admin_client.get(url).json()
    assert body["period"] == "30d"
    assert body["header"]["new_in_period"] == 1      # dates did not narrow the preset window


def test_custom_range_does_not_move_reaction_windows(admin_client, db_session):
    """2h header window keys off ``now``, not the selected range (FR-003); the
    attention block (feature 015) is latched state, identical across any range."""
    org = _org(db_session)
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(minutes=30),
            review_date=_d(0), sentiment="negative", hash_="fresh")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=8), review_date=_d(8), hash_="old")
    _seed_arm_sweep(db_session, window_days=5, period_days=30)

    preset = admin_client.get("/api/dashboard/overview?period=30d").json()
    ranged = admin_client.get(_range_url(_d(10), _d(5))).json()

    assert ranged["header"]["new_in_period"] == 1                  # only the 8-days-ago review
    assert ranged["header"]["fresh_negatives_2h"] == preset["header"]["fresh_negatives_2h"] == 1
    assert len(ranged["attention"]) == len(preset["attention"])


def test_custom_range_combines_with_company_platform_and_orgs(admin_client, db_session):
    from app.models.company import Company

    comp = Company(name="Chain 013")
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)

    inside = _org(db_session, name="Inside", company_id=comp.id)
    other = _org(db_session, name="Outside")
    # in range + right company + right platform -> the only counted review
    _review(db_session, inside, rating=5, first_seen=NOW - timedelta(days=7), review_date=_d(7), hash_="hit")
    _review(db_session, inside, rating=5, first_seen=NOW - timedelta(days=7), review_date=_d(7),
            hash_="wrong_platform", platform=ReviewPlatform.gis2)
    _review(db_session, inside, rating=5, first_seen=NOW - timedelta(days=1), review_date=_d(1), hash_="out_of_range")
    _review(db_session, other, rating=5, first_seen=NOW - timedelta(days=7), review_date=_d(7), hash_="other_company")

    body = admin_client.get(
        _range_url(_d(10), _d(5), company_id=comp.id, platform="yandex", org_ids=inside.id)
    ).json()
    assert body["header"]["new_in_period"] == 1


def test_company_filter_excludes_orgs_without_company(admin_client, db_session):
    from app.models.company import Company

    comp = Company(name="Branded")
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)

    branded = _org(db_session, name="Branded branch", company_id=comp.id)
    orphan = _org(db_session, name="No brand")
    _review(db_session, branded, rating=5, first_seen=NOW - timedelta(hours=1), hash_="b")
    _review(db_session, orphan, rating=5, first_seen=NOW - timedelta(hours=1), hash_="o")

    scoped = admin_client.get(f"/api/dashboard/overview?company_id={comp.id}&period=all").json()
    unscoped = admin_client.get("/api/dashboard/overview?period=all").json()
    assert scoped["kpi_hero"]["total_reviews"] == 1
    assert unscoped["kpi_hero"]["total_reviews"] == 2
