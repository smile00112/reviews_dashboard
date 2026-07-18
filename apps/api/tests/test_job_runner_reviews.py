import uuid

import pytest

from app.models.enums import (
    JobItemStatus,
    JobKind,
    JobRunStatus,
    JobTrigger,
    ReviewPlatform,
    ScrapeMode,
    ScrapeRunStatus,
)
from app.models.job import Job
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.models.review import Review
from app.models.scrape_run import ScrapeRun
from app.services.job_runner import JobRunner
from app.services.job_service import JobService


class FakeScrapeService:
    """Пишет ScrapeRun как настоящий сервис, но ничего не скрапит."""

    def __init__(self, db, inserted=3, status=ScrapeRunStatus.success):
        self.db = db
        self.inserted = inserted
        self.status = status
        self.executed: list[uuid.UUID] = []

    def create_run(self, organization_id, mode):
        run = ScrapeRun(organization_id=organization_id, mode=mode, status=ScrapeRunStatus.queued)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def execute_run(self, run_id, limit=None, max_pages=None):
        self.executed.append(run_id)
        run = self.db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
        run.status = self.status
        run.reviews_seen = self.inserted
        run.reviews_inserted = self.inserted
        run.reviews_updated = 0
        self.db.commit()


@pytest.fixture()
def reviews_job(db_session):
    job = Job(kind=JobKind.reviews, platform=ReviewPlatform.yandex, options={"delay_seconds": 0})
    db_session.add(job)
    db_session.commit()
    return job


def _org(db_session, *, review_count):
    org = Organization(
        name="Org", yandex_url="https://yandex.ru/maps/org/1", review_count=review_count
    )
    db_session.add(org)
    db_session.commit()
    return org


def _gis2_org(db_session, *, gis2_review_count):
    org = Organization(
        name="Org", gis2_url="https://2gis.ru/org/1", gis2_review_count=gis2_review_count
    )
    db_session.add(org)
    db_session.commit()
    return org


def _seed_reviews(db_session, org, count, *, platform=ReviewPlatform.yandex, scrape_mode=ScrapeMode.public_http, prefix=""):
    for i in range(count):
        db_session.add(
            Review(
                organization_id=org.id,
                platform=platform,
                scrape_mode=scrape_mode,
                content_hash=f"hash-{prefix}{i}",
                author_name="A",
                rating=5,
                review_text="text",
            )
        )
    db_session.commit()


def test_skips_when_counts_match(db_session, reviews_job):
    org = _org(db_session, review_count=2)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.skipped
    assert "2" in item.reason
    assert item.scrape_run_id is None
    assert scrape.executed == []
    db_session.refresh(run)
    assert run.status is JobRunStatus.success
    assert run.orgs_skipped == 1


def test_skips_when_platform_count_unknown(db_session, reviews_job):
    _org(db_session, review_count=None)
    scrape = FakeScrapeService(db_session)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.skipped
    assert scrape.executed == []


def test_scrapes_when_counts_differ_and_links_scrape_run(db_session, reviews_job):
    org = _org(db_session, review_count=5)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session, inserted=3)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.success
    assert item.scrape_run_id is not None
    assert item.payload["platform_total"] == 5
    assert item.payload["scraped_before"] == 2
    assert item.payload["inserted"] == 3
    assert len(scrape.executed) == 1

    linked = db_session.query(ScrapeRun).filter(ScrapeRun.id == item.scrape_run_id).one()
    assert linked.mode is ScrapeMode.public_http


def test_failed_scrape_run_marks_item_failed(db_session, reviews_job):
    org = _org(db_session, review_count=5)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session, inserted=0, status=ScrapeRunStatus.failed)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.failed
    db_session.refresh(run)
    assert run.status is JobRunStatus.failed


def test_skips_when_platform_count_lower_than_collected(db_session, reviews_job):
    # Отзывы могли быть удалены на площадке: счётчик площадки ниже уже
    # собранного — это не "совпадают", и скрапер запускаться не должен.
    org = _org(db_session, review_count=3)
    _seed_reviews(db_session, org, 5)
    scrape = FakeScrapeService(db_session)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.skipped
    assert "3" in item.reason and "5" in item.reason
    assert "совпадают" not in item.reason
    assert item.scrape_run_id is None
    assert scrape.executed == []
    db_session.refresh(run)
    assert run.status is JobRunStatus.success
    assert run.orgs_skipped == 1


def test_needs_manual_action_scrape_run_maps_to_item_status(db_session, reviews_job):
    org = _org(db_session, review_count=5)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session, inserted=0, status=ScrapeRunStatus.needs_manual_action)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.needs_manual_action
    db_session.refresh(run)
    assert run.status is JobRunStatus.needs_manual_action


@pytest.fixture()
def gis2_reviews_job(db_session):
    job = Job(kind=JobKind.reviews, platform=ReviewPlatform.gis2, options={"delay_seconds": 0})
    db_session.add(job)
    db_session.commit()
    return job


def test_scrapes_gis2_org_and_counts_only_gis2_reviews(db_session, gis2_reviews_job):
    org = _gis2_org(db_session, gis2_review_count=5)
    # Собранные ранее отзывы по обеим площадкам: должны учитываться только
    # gis2 — иначе перепутанный _PLATFORM_ENUM_BY_KEY останется незамеченным.
    _seed_reviews(db_session, org, 2, platform=ReviewPlatform.gis2, scrape_mode=ScrapeMode.twogis_api, prefix="gis2-")
    _seed_reviews(db_session, org, 10, platform=ReviewPlatform.yandex, scrape_mode=ScrapeMode.public_http, prefix="yandex-")
    scrape = FakeScrapeService(db_session, inserted=3)
    run = JobService(db_session).create_run(gis2_reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.success
    assert item.payload["platform_total"] == 5
    # Only the 2 gis2 reviews count, not the 10 yandex ones for the same org.
    assert item.payload["scraped_before"] == 2
    assert len(scrape.executed) == 1

    linked = db_session.query(ScrapeRun).filter(ScrapeRun.id == item.scrape_run_id).one()
    assert linked.mode is ScrapeMode.twogis_api
