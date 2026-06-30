from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.scraper.types import ParsedReview
from app.services.review_service import ReviewService


def _make_org(db):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db.add(org)
    db.commit()
    return org


def _seed(db, org, specs):
    reviews = [
        ParsedReview(author_name=f"u{i}", rating=rating, review_text=text, review_date_text=str(i))
        for i, (rating, text) in enumerate(specs)
    ]
    ReviewService(db).upsert_reviews(org.id, reviews, ScrapeMode.public)


def test_summary_distribution_and_problems(client, db_session):
    org = _make_org(db_session)
    _seed(
        db_session,
        org,
        [
            (5, "Очень вкусно и отлично"),       # positive
            (5, "Прекрасно, чисто, удобно"),      # positive
            (1, "Ужасно грязно и долго ждать"),   # negative + problems
            (2, "Невкусно, дорого"),              # negative + problems
            (3, "Был в среду после обеда"),       # neutral
        ],
    )

    resp = client.get(f"/api/organizations/{org.id}/analytics")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_reviews"] == 5
    assert body["analyzed_reviews"] == 5
    assert body["sentiment_distribution"]["positive"] == 2
    assert body["sentiment_distribution"]["negative"] == 2
    assert body["sentiment_distribution"]["neutral"] == 1
    assert body["reviews_with_problems"] >= 2
    assert any(c["category"] for c in body["top_problem_categories"])


def test_summary_detects_rating_sentiment_mismatch(client, db_session):
    org = _make_org(db_session)
    # 5 stars but strongly negative text -> mismatch.
    _seed(db_session, org, [(5, "Ужасно невкусно, кошмар, отвратительно")])

    body = client.get(f"/api/organizations/{org.id}/analytics").json()
    assert body["rating_sentiment_mismatch_count"] == 1


def test_summary_empty_org_is_zeroed(client, db_session):
    org = _make_org(db_session)
    resp = client.get(f"/api/organizations/{org.id}/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_reviews"] == 0
    assert body["analyzed_reviews"] == 0
    assert body["average_sentiment_score"] == 0.0
    assert body["top_problem_categories"] == []


def test_analytics_unknown_org_404(client):
    resp = client.get("/api/organizations/00000000-0000-0000-0000-000000000000/analytics")
    assert resp.status_code == 404


def test_analyze_endpoint_backfills(client, db_session):
    org = _make_org(db_session)
    _seed(db_session, org, [(1, "Грязно"), (5, "Отлично")])

    resp = client.post(f"/api/organizations/{org.id}/analyze")
    assert resp.status_code == 200
    assert resp.json()["analyzed"] == 2
