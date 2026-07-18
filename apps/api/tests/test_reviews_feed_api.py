"""Feed filters for GET /api/reviews (reviews page rebuild).

Tab semantics: answered = has response_text, unanswered = none,
in_progress / escalated = by Review.status. Aspect filter matches
problems JSONB in Python (SQLite backend has no JSONB operators).
"""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _org(db, **kw):
    org = Organization(name=kw.pop("name", "Org"), **kw)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, hash_, rating=5, first_seen=None, review_date=None,
            response_text=None, status=None, platform=ReviewPlatform.yandex,
            is_paid=False, problems=None, sentiment=None):
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
        review_date=review_date,
        status=status,
        is_paid=is_paid,
        problems=problems,
        sentiment=sentiment,
    )
    db.add(r)
    db.commit()
    return r


def _ids(resp):
    return [item["id"] for item in resp.json()["items"]]


def test_status_tab_filters(client, db_session):
    org = _org(db_session)
    answered = _review(db_session, org, hash_="h1", response_text="спасибо")
    unanswered = _review(db_session, org, hash_="h2")
    in_progress = _review(db_session, org, hash_="h3", status=ReviewStatus.in_progress)
    escalated = _review(db_session, org, hash_="h4", status=ReviewStatus.escalated)

    assert str(answered.id) in _ids(client.get("/api/reviews?status=answered"))
    assert str(answered.id) not in _ids(client.get("/api/reviews?status=unanswered"))
    # escalated has no response -> also in unanswered (tabs overlap by design)
    assert str(escalated.id) in _ids(client.get("/api/reviews?status=unanswered"))
    assert _ids(client.get("/api/reviews?status=in_progress")) == [str(in_progress.id)]
    assert _ids(client.get("/api/reviews?status=escalated")) == [str(escalated.id)]
    assert len(_ids(client.get("/api/reviews?status=all"))) == 4


def test_platform_and_tone_filters(client, db_session):
    org = _org(db_session)
    ya_neg = _review(db_session, org, hash_="h1", rating=2, platform=ReviewPlatform.yandex)
    gis_pos = _review(db_session, org, hash_="h2", rating=5, platform=ReviewPlatform.gis2)

    assert _ids(client.get("/api/reviews?platform=gis2")) == [str(gis_pos.id)]
    assert _ids(client.get("/api/reviews?tone=neg")) == [str(ya_neg.id)]
    assert _ids(client.get("/api/reviews?tone=pos")) == [str(gis_pos.id)]


def test_period_filter_uses_review_date_with_first_seen_fallback(client, db_session):
    org = _org(db_session)
    fresh = _review(db_session, org, hash_="h1", review_date=NOW.date())
    old = _review(db_session, org, hash_="h2", review_date=(NOW - timedelta(days=200)).date())
    # No review_date -> falls back to first_seen_at date
    dateless_fresh = _review(db_session, org, hash_="h3", first_seen=NOW - timedelta(days=2))

    ids_30d = _ids(client.get("/api/reviews?period=30d"))
    assert str(fresh.id) in ids_30d
    assert str(dateless_fresh.id) in ids_30d
    assert str(old.id) not in ids_30d
    assert str(old.id) in _ids(client.get("/api/reviews?period=year"))


def test_is_paid_filter(client, db_session):
    org = _org(db_session)
    paid = _review(db_session, org, hash_="h1", is_paid=True)
    _review(db_session, org, hash_="h2")
    assert _ids(client.get("/api/reviews?is_paid=true")) == [str(paid.id)]


def test_aspect_filter_matches_problems_category(client, db_session):
    org = _org(db_session)
    with_aspect = _review(
        db_session, org, hash_="h1", rating=2,
        problems=[{"category": "ожидание", "description": "d", "keywords_found": ["долго ждать"], "severity": "low", "context": "c"}],
    )
    _review(db_session, org, hash_="h2", problems=[])
    _review(db_session, org, hash_="h3", problems=None)

    resp = client.get("/api/reviews?aspect=ожидание")
    assert _ids(resp) == [str(with_aspect.id)]
    assert resp.json()["total"] == 1


def test_sort_criticality_unanswered_low_rating_first(client, db_session):
    org = _org(db_session)
    answered_bad = _review(db_session, org, hash_="h1", rating=1, response_text="reply")
    unanswered_good = _review(db_session, org, hash_="h2", rating=5)
    unanswered_bad = _review(db_session, org, hash_="h3", rating=1)

    ids = _ids(client.get("/api/reviews?sort=criticality"))
    assert ids[0] == str(unanswered_bad.id)
    assert ids[1] == str(unanswered_good.id)
    assert ids[2] == str(answered_bad.id)


def test_response_includes_triage_fields(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", status=ReviewStatus.escalated, is_paid=True,
            platform=ReviewPlatform.gis2)
    item = client.get("/api/reviews").json()["items"][0]
    assert item["status"] == "escalated"
    assert item["is_paid"] is True
    assert item["paid_cost"] is None
    assert item["platform"] == "gis2"


def test_invalid_enum_params_return_422(client):
    assert client.get("/api/reviews?status=bogus").status_code == 422
    assert client.get("/api/reviews?tone=bogus").status_code == 422
    assert client.get("/api/reviews?period=bogus").status_code == 422
    assert client.get("/api/reviews?sort=bogus").status_code == 422
