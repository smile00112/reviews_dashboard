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

    items = admin_client.get("/api/dashboard/overview?period=all").json()["attention"]
    spikes = [i for i in items if i["type"] == "aspect_spike"]
    assert spikes and "опоздание" in spikes[0]["title"]


def test_attention_rating_drop_needs_history(admin_client, db_session):
    from app.models.enums import ReviewPlatform
    from app.services.dashboard_service import DashboardService

    org = _org(db_session, rating=4.2)
    # No snapshot yet -> no rating_drop item.
    body = admin_client.get("/api/dashboard/overview?period=30d").json()
    assert not any(i["type"] == "rating_drop" for i in body["attention"])

    # Snapshot 30d ago at 4.5, current 4.2 -> delta -0.3 -> drop appears.
    old = datetime(NOW.year, NOW.month, NOW.day, tzinfo=timezone.utc) - timedelta(days=29)
    org.rating = 4.5
    db_session.commit()
    DashboardService(db_session).capture_snapshot(org.id, ReviewPlatform.yandex, now=old)
    org.rating = 4.2
    db_session.commit()

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
