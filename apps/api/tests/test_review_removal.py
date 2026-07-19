"""Removal tracking (feature 011): marking, un-marking, scoping, zero-guard.

Contract: only a successful full pass may mark removals; a review seen again is
un-marked on its existing row (dedup contract untouched); marking is scoped to
the pass's organization + platform.
"""

from datetime import datetime, timezone

from app.models.enums import ReviewPlatform, ScrapeMode, ScrapeRunStatus
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.normalize import build_review_hash
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.review_service import ReviewService
from app.services.scrape_service import ScrapeService

NOW = datetime.now(timezone.utc)

R1 = ParsedReview(author_name="Anna", rating=5, review_text="Great place", review_date_text="1 Jan")
R2 = ParsedReview(author_name="Boris", rating=2, review_text="Slow service", review_date_text="2 Jan")
R3 = ParsedReview(author_name="Clara", rating=4, review_text="Nice food", review_date_text="3 Jan")


def _org(db_session, review_count: int | None = None) -> Organization:
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public_http,
        review_count=review_count,
    )
    db_session.add(org)
    db_session.commit()
    return org


class FakeHttpScraper:
    def __init__(self, result: ScrapeResult):
        self.result = result
        self.calls: list[dict] = []

    def scrape(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _run_http_scrape(db_session, org, reviews, *, full_pass: bool) -> object:
    result = ScrapeResult(
        organization=ParsedOrganization(name="Org", review_count=len(reviews)),
        reviews=list(reviews),
        full_pass=full_pass,
    )
    service = ScrapeService(db_session, http_scraper=FakeHttpScraper(result))
    run = service.create_run(org.id, ScrapeMode.public_http)
    service.execute_run(run.id)
    db_session.refresh(run)
    return run


# --- mark_removed_missing (service unit) ---------------------------------


def test_full_pass_marks_missing_review_removed(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)
    service.upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)

    removed = service.mark_removed_missing(org.id, ReviewPlatform.yandex, [R1], NOW)
    assert removed == 1

    rows = {r.author_name: r for r in db_session.query(Review).all()}
    assert rows["Anna"].removed_at is None
    assert rows["Boris"].removed_at is not None


def test_marking_is_idempotent(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)
    service.upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)
    assert service.mark_removed_missing(org.id, ReviewPlatform.yandex, [R1], NOW) == 1
    # Second identical pass: already-removed row is not re-marked.
    assert service.mark_removed_missing(org.id, ReviewPlatform.yandex, [R1], NOW) == 0


def test_marking_scoped_to_platform(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)
    service.upsert_reviews(org.id, [R1], ScrapeMode.public_http)   # yandex
    service.upsert_reviews(org.id, [R2], ScrapeMode.twogis_api)    # gis2

    # A yandex full pass seeing nothing must never touch the gis2 row.
    service.mark_removed_missing(org.id, ReviewPlatform.yandex, [], NOW)
    rows = {r.author_name: r for r in db_session.query(Review).all()}
    assert rows["Anna"].removed_at is not None
    assert rows["Boris"].removed_at is None


def test_marking_scoped_to_organization(db_session):
    org1 = _org(db_session)
    org2 = Organization(
        yandex_url="https://yandex.ru/maps/org/other/456/",
        normalized_url="https://yandex.ru/maps/org/other/456",
        preferred_scrape_mode=ScrapeMode.public_http,
    )
    db_session.add(org2)
    db_session.commit()
    service = ReviewService(db_session)
    service.upsert_reviews(org1.id, [R1], ScrapeMode.public_http)
    service.upsert_reviews(org2.id, [R1], ScrapeMode.public_http)

    service.mark_removed_missing(org1.id, ReviewPlatform.yandex, [], NOW)
    org2_row = db_session.query(Review).filter(Review.organization_id == org2.id).one()
    assert org2_row.removed_at is None


def test_reappeared_review_is_unmarked_not_duplicated(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)
    service.upsert_reviews(org.id, [R1], ScrapeMode.public_http)
    service.mark_removed_missing(org.id, ReviewPlatform.yandex, [], NOW)
    row = db_session.query(Review).one()
    assert row.removed_at is not None
    hash_before = row.content_hash

    seen, inserted, updated = service.upsert_reviews(org.id, [R1], ScrapeMode.public_http)
    assert (seen, inserted, updated) == (1, 0, 1)
    row = db_session.query(Review).one()  # still exactly one row
    assert row.removed_at is None
    assert row.content_hash == hash_before == build_review_hash(
        R1.author_name, R1.rating, R1.review_date_text, R1.review_text
    )


# --- scrape pipeline integration -----------------------------------------


def test_full_pass_run_marks_and_records_flag(db_session):
    org = _org(db_session, review_count=1)
    ReviewService(db_session).upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)

    run = _run_http_scrape(db_session, org, [R1], full_pass=True)
    assert run.status == ScrapeRunStatus.success
    assert run.full_pass is True

    rows = {r.author_name: r for r in db_session.query(Review).all()}
    assert rows["Anna"].removed_at is None
    assert rows["Boris"].removed_at is not None


def test_partial_pass_never_marks(db_session):
    org = _org(db_session, review_count=1)
    ReviewService(db_session).upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)

    run = _run_http_scrape(db_session, org, [R1], full_pass=False)
    assert run.status == ScrapeRunStatus.success
    assert run.full_pass is False
    assert all(r.removed_at is None for r in db_session.query(Review).all())


def test_zero_full_pass_with_nonzero_counter_is_anomaly(db_session):
    # Platform counter says 128 but a "successful full pass" saw nothing:
    # indistinguishable from a parser regression -> fail loudly, mark nothing.
    org = _org(db_session, review_count=128)
    ReviewService(db_session).upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)

    run = _run_http_scrape(db_session, org, [], full_pass=True)
    assert run.status == ScrapeRunStatus.failed
    assert run.error_code == "empty_full_pass"
    assert all(r.removed_at is None for r in db_session.query(Review).all())


def test_zero_full_pass_with_zero_counter_marks_all(db_session):
    # Counter corroborates the wipe-out -> legitimate mass removal.
    org = _org(db_session, review_count=0)
    ReviewService(db_session).upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)

    run = _run_http_scrape(db_session, org, [], full_pass=True)
    assert run.status == ScrapeRunStatus.success
    assert all(r.removed_at is not None for r in db_session.query(Review).all())


def test_zero_full_pass_with_no_prior_reviews_is_success(db_session):
    # Nothing collected before: an empty full pass is unremarkable.
    org = _org(db_session, review_count=0)
    run = _run_http_scrape(db_session, org, [], full_pass=True)
    assert run.status == ScrapeRunStatus.success


def test_exhausted_pagination_below_platform_counter_is_not_full(db_session):
    # Yandex serves at most ~600 reviews over ?page=N: pagination "exhausts"
    # while most of a big org's list was never seen. The counter (1110 vs 2
    # seen) disproves coverage -> no marking, run recorded as partial.
    org = _org(db_session, review_count=1110)
    ReviewService(db_session).upsert_reviews(org.id, [R1, R2, R3], ScrapeMode.public_http)

    run = _run_http_scrape(db_session, org, [R1, R2], full_pass=True)
    assert run.status == ScrapeRunStatus.success
    assert run.full_pass is False
    assert all(r.removed_at is None for r in db_session.query(Review).all())


def test_counter_unknown_never_marks(db_session):
    # No platform counter -> coverage cannot be corroborated -> partial.
    org = _org(db_session, review_count=None)
    ReviewService(db_session).upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)

    run = _run_http_scrape(db_session, org, [R1], full_pass=True)
    assert run.status == ScrapeRunStatus.success
    assert run.full_pass is False
    assert all(r.removed_at is None for r in db_session.query(Review).all())


# --- API contract: removed filter ----------------------------------------


def _seed_one_removed(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)
    service.upsert_reviews(org.id, [R1, R2], ScrapeMode.public_http)
    service.mark_removed_missing(org.id, ReviewPlatform.yandex, [R1], NOW)  # Boris removed
    return org


def test_api_default_list_hides_removed(client, db_session):
    org = _seed_one_removed(db_session)
    body = client.get(f"/api/organizations/{org.id}/reviews").json()
    assert body["total"] == 1
    assert body["items"][0]["author_name"] == "Anna"
    assert body["items"][0]["removed_at"] is None


def test_api_removed_view_shows_only_removed_with_timestamp(client, db_session):
    org = _seed_one_removed(db_session)
    body = client.get(f"/api/organizations/{org.id}/reviews", params={"removed": "removed"}).json()
    assert body["total"] == 1
    assert body["items"][0]["author_name"] == "Boris"
    assert body["items"][0]["removed_at"] is not None


def test_api_all_view_shows_both(client, db_session):
    org = _seed_one_removed(db_session)
    body = client.get(f"/api/organizations/{org.id}/reviews", params={"removed": "all"}).json()
    assert body["total"] == 2


def test_api_global_feed_hides_removed_by_default(client, db_session):
    _seed_one_removed(db_session)
    body = client.get("/api/reviews").json()
    assert body["total"] == 1
    assert body["items"][0]["author_name"] == "Anna"


def test_api_invalid_removed_value_is_422(client, db_session):
    org = _seed_one_removed(db_session)
    response = client.get(f"/api/organizations/{org.id}/reviews", params={"removed": "bogus"})
    assert response.status_code == 422
