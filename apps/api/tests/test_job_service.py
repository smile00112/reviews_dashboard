import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import JobItemStatus, JobKind, JobRunStatus, JobTrigger, ReviewPlatform
from app.models.job import Job
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.services.job_service import (
    JOB_RUN_RETENTION_DAYS,
    InvalidCron,
    JobAlreadyRunning,
    JobService,
)


@pytest.fixture()
def job(db_session):
    job = Job(kind=JobKind.org_metrics, platform=ReviewPlatform.yandex, schedule_cron="0 4 * * *")
    db_session.add(job)
    db_session.commit()
    return job


def test_create_run_rejects_second_active_run(db_session, job):
    service = JobService(db_session)
    first = service.create_run(job.id, JobTrigger.manual)
    first.status = JobRunStatus.running
    db_session.commit()

    with pytest.raises(JobAlreadyRunning):
        service.create_run(job.id, JobTrigger.schedule)


def test_create_run_allowed_after_previous_finished(db_session, job):
    service = JobService(db_session)
    first = service.create_run(job.id, JobTrigger.manual)
    first.status = JobRunStatus.success
    db_session.commit()

    second = service.create_run(job.id, JobTrigger.schedule)
    assert second.id != first.id
    assert second.trigger is JobTrigger.schedule


def test_update_job_rejects_invalid_cron(db_session, job):
    service = JobService(db_session)
    with pytest.raises(InvalidCron):
        service.update_job(job.id, schedule_cron="не крон")

    updated = service.update_job(job.id, schedule_cron="*/30 * * * *", is_enabled=True)
    assert updated.schedule_cron == "*/30 * * * *"
    assert updated.is_enabled is True


def test_purge_removes_runs_older_than_retention_with_items(db_session, job):
    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1")
    db_session.add(org)
    db_session.commit()

    now = datetime.now(timezone.utc)
    old = JobRun(
        job_id=job.id, trigger=JobTrigger.schedule, status=JobRunStatus.success,
        started_at=now - timedelta(days=JOB_RUN_RETENTION_DAYS + 1),
    )
    fresh = JobRun(
        job_id=job.id, trigger=JobTrigger.schedule, status=JobRunStatus.success,
        started_at=now - timedelta(days=JOB_RUN_RETENTION_DAYS - 1),
    )
    db_session.add_all([old, fresh])
    db_session.commit()
    db_session.add(JobRunItem(job_run_id=old.id, organization_id=org.id, status=JobItemStatus.success))
    db_session.commit()

    deleted = JobService(db_session).purge_old_runs(now=now)

    assert deleted == 1
    assert db_session.query(JobRun).count() == 1
    assert db_session.query(JobRunItem).count() == 0


def test_fail_interrupted_runs_marks_queued_and_running_only(db_session, job):
    running = JobRun(job_id=job.id, trigger=JobTrigger.manual, status=JobRunStatus.running)
    queued = JobRun(job_id=job.id, trigger=JobTrigger.schedule, status=JobRunStatus.queued)
    success = JobRun(job_id=job.id, trigger=JobTrigger.manual, status=JobRunStatus.success)
    db_session.add_all([running, queued, success])
    db_session.commit()

    count = JobService(db_session).fail_interrupted_runs()

    assert count == 2
    db_session.refresh(running)
    db_session.refresh(queued)
    db_session.refresh(success)

    for run in (running, queued):
        assert run.status == JobRunStatus.failed
        assert run.error_message == "interrupted by API restart"
        assert run.finished_at is not None

    assert success.status == JobRunStatus.success
    assert success.error_message is None
    assert success.finished_at is None


def test_list_runs_filters_by_job_and_status(db_session, job):
    other = Job(kind=JobKind.reviews, platform=ReviewPlatform.gis2)
    db_session.add(other)
    db_session.commit()
    db_session.add_all([
        JobRun(job_id=job.id, trigger=JobTrigger.manual, status=JobRunStatus.failed),
        JobRun(job_id=other.id, trigger=JobTrigger.manual, status=JobRunStatus.success),
    ])
    db_session.commit()

    service = JobService(db_session)
    assert len(service.list_runs(job_id=job.id)) == 1
    assert len(service.list_runs(status=JobRunStatus.success)) == 1
    assert len(service.list_runs()) == 2
