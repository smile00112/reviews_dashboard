"""Aspect aggregation from problems JSONB (fixed local taxonomy, no LLM).

delta_pct compares the selected window against the previous window of equal
length; None when the previous window had zero mentions."""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _org(db):
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, hash_, days_ago, categories, sentiment="negative", rating=2):
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex,
        rating=rating,
        review_text="text",
        content_hash=hash_,
        first_seen_at=NOW - timedelta(days=days_ago),
        last_seen_at=NOW,
        review_date=(NOW - timedelta(days=days_ago)).date(),
        sentiment=sentiment,
        problems=[
            {"category": c, "description": "d", "keywords_found": ["k"], "severity": "low", "context": ""}
            for c in categories
        ],
    )
    db.add(r)
    db.commit()
    return r


def test_aspects_mentions_delta_and_sentiment(client, db_session):
    org = _org(db_session)
    # current 30d window: 2 mentions of "ожидание" (1 neg, 1 pos)
    _review(db_session, org, hash_="h1", days_ago=5, categories=["ожидание"], sentiment="negative")
    _review(db_session, org, hash_="h2", days_ago=10, categories=["ожидание"], sentiment="positive", rating=4)
    # previous window (30..60 days back): 1 mention
    _review(db_session, org, hash_="h3", days_ago=45, categories=["ожидание"])
    # different aspect, current window only -> delta None
    _review(db_session, org, hash_="h4", days_ago=3, categories=["чистота"])

    body = client.get("/api/reviews/aspects?period=30d").json()
    by_cat = {a["category"]: a for a in body["aspects"]}

    waiting = by_cat["ожидание"]
    assert waiting["mentions"] == 2
    assert waiting["delta_pct"] == 100          # 2 vs 1
    assert waiting["pos"] == 50 and waiting["neg"] == 50 and waiting["neu"] == 0
    assert waiting["label"] == "Ожидание"

    clean = by_cat["чистота"]
    assert clean["mentions"] == 1
    assert clean["delta_pct"] is None           # nothing in previous window
    assert body["trend"] is None


def test_aspects_trend_series_90_days(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", days_ago=1, categories=["ожидание"])
    _review(db_session, org, hash_="h2", days_ago=1, categories=["ожидание"])
    _review(db_session, org, hash_="h3", days_ago=80, categories=["ожидание"])
    _review(db_session, org, hash_="h4", days_ago=100, categories=["ожидание"])  # outside 90d

    body = client.get("/api/reviews/aspects?period=30d&aspect=ожидание").json()
    trend = body["trend"]
    assert trend["category"] == "ожидание"
    assert trend["days"] == 90
    assert len(trend["series"]) == 91           # today + 90 days back, zero-filled
    assert sum(p["count"] for p in trend["series"]) == 3
    yesterday = (NOW - timedelta(days=1)).date().isoformat()
    assert {"date": yesterday, "count": 2} in trend["series"]


def test_aspects_empty_db(client):
    body = client.get("/api/reviews/aspects").json()
    assert body == {"aspects": [], "trend": None}
