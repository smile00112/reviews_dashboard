"""Tab counters for the reviews page. Counters respect the secondary filters
(platform/tone/period/org/aspect) but never the status tab itself."""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _org(db):
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, hash_, rating=5, first_seen=None, response_text=None,
            status=None, platform=ReviewPlatform.yandex):
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
        response_text=response_text,
        response_first_seen_at=NOW if response_text else None,
        status=status,
    )
    db.add(r)
    db.commit()
    return r


def test_summary_counts(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", response_text="ok")                     # answered
    _review(db_session, org, hash_="h2", rating=2)                               # unanswered, negative, fresh
    _review(db_session, org, hash_="h3", rating=1, first_seen=NOW - timedelta(hours=30))  # unanswered overdue, negative
    _review(db_session, org, hash_="h4", status=ReviewStatus.in_progress)        # unanswered, in progress
    _review(db_session, org, hash_="h5", status=ReviewStatus.escalated,
            first_seen=NOW - timedelta(days=10))                                 # unanswered overdue, not "new"

    body = client.get("/api/reviews/summary").json()
    assert body["total"] == 5
    assert body["answered"] == 1
    assert body["unanswered"] == 4
    assert body["in_progress"] == 1
    assert body["escalated"] == 1
    assert body["overdue_24h"] == 2      # h3, h5
    assert body["negative"] == 2         # h2, h3
    assert body["new_count"] == 4        # first_seen within 7d: h1,h2,h3,h4


def test_summary_respects_secondary_filters(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", rating=2, platform=ReviewPlatform.yandex)
    _review(db_session, org, hash_="h2", rating=5, platform=ReviewPlatform.gis2)

    body = client.get("/api/reviews/summary?platform=gis2").json()
    assert body["total"] == 1
    assert body["negative"] == 0


def test_summary_empty_db_zeroes(client):
    body = client.get("/api/reviews/summary").json()
    assert body == {
        "total": 0, "new_count": 0, "unanswered": 0, "in_progress": 0,
        "escalated": 0, "answered": 0, "overdue_24h": 0, "negative": 0,
    }
