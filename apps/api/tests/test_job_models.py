import uuid
from datetime import datetime, timezone

from app.models.enums import JobItemStatus, JobKind, JobRunStatus, JobTrigger, ReviewPlatform
from app.models.job import Job
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization


def test_job_run_item_cascades_and_defaults(db_session):
    job = Job(kind=JobKind.org_metrics, platform=ReviewPlatform.yandex, schedule_cron="0 4 * * *")
    db_session.add(job)
    db_session.commit()

    assert job.is_enabled is False
    assert job.options == {}
    assert job.timezone == "Europe/Moscow"

    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1")
    db_session.add(org)
    db_session.commit()

    run = JobRun(job_id=job.id, trigger=JobTrigger.manual, status=JobRunStatus.running)
    db_session.add(run)
    db_session.commit()
    assert run.orgs_total == 0

    item = JobRunItem(
        job_run_id=run.id,
        organization_id=org.id,
        status=JobItemStatus.skipped,
        reason="счётчики совпадают: 42 = 42",
        payload={"platform_total": 42, "scraped_before": 42},
    )
    db_session.add(item)
    db_session.commit()

    assert run.items[0].payload["platform_total"] == 42

    db_session.delete(run)
    db_session.commit()
    assert db_session.query(JobRunItem).count() == 0


def test_job_unique_per_kind_and_platform(db_session):
    from sqlalchemy.exc import IntegrityError

    db_session.add(Job(kind=JobKind.reviews, platform=ReviewPlatform.gis2))
    db_session.commit()
    db_session.add(Job(kind=JobKind.reviews, platform=ReviewPlatform.gis2))
    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:
        raise AssertionError("duplicate (kind, platform) must be rejected")
