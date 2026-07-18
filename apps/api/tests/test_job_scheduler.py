from app.models.enums import JobKind, JobRunStatus, ReviewPlatform
from app.models.job import Job
from app.models.job_run import JobRun
from app.services.job_scheduler import RETENTION_JOB_ID, JobScheduler


def _job(db_session, *, cron, enabled):
    job = Job(
        kind=JobKind.org_metrics, platform=ReviewPlatform.yandex,
        schedule_cron=cron, is_enabled=enabled,
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_sync_registers_only_enabled_jobs_with_cron(db_session):
    enabled = _job(db_session, cron="0 4 * * *", enabled=True)
    disabled = Job(
        kind=JobKind.reviews, platform=ReviewPlatform.yandex,
        schedule_cron="0 5 * * *", is_enabled=False,
    )
    db_session.add(disabled)
    db_session.commit()

    scheduler = JobScheduler()
    scheduler.sync_all(db_session)

    ids = {j.id for j in scheduler._scheduler.get_jobs()}
    assert str(enabled.id) in ids
    assert str(disabled.id) not in ids
    assert RETENTION_JOB_ID in ids


def test_reschedule_removes_trigger_when_job_disabled(db_session):
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    scheduler = JobScheduler()
    scheduler.sync_all(db_session)
    assert scheduler._scheduler.get_job(str(job.id)) is not None

    job.is_enabled = False
    db_session.commit()
    scheduler.reschedule_job(job, db_session)

    assert scheduler._scheduler.get_job(str(job.id)) is None


def test_next_run_at_is_written_back(db_session):
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    scheduler = JobScheduler()
    scheduler.sync_all(db_session)
    db_session.refresh(job)
    assert job.next_run_at is not None


def test_reschedule_reenable_restores_trigger_and_next_run_at(db_session):
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    scheduler = JobScheduler()
    scheduler.sync_all(db_session)
    assert scheduler._scheduler.get_job(str(job.id)) is not None

    job.is_enabled = False
    db_session.commit()
    scheduler.reschedule_job(job, db_session)
    assert scheduler._scheduler.get_job(str(job.id)) is None
    db_session.expire_all()
    disabled = db_session.query(Job).filter(Job.id == job.id).first()
    assert disabled.next_run_at is None

    disabled.is_enabled = True
    db_session.commit()
    scheduler.reschedule_job(disabled, db_session)

    assert scheduler._scheduler.get_job(str(job.id)) is not None
    db_session.expire_all()
    reenabled = db_session.query(Job).filter(Job.id == job.id).first()
    assert reenabled.next_run_at is not None


def test_reschedule_clears_next_run_at_when_cron_removed(db_session):
    """Job stays enabled but its cron is cleared: the trigger must be removed
    and next_run_at must go back to NULL rather than keeping a stale value."""
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    scheduler = JobScheduler()
    scheduler.sync_all(db_session)
    assert scheduler._scheduler.get_job(str(job.id)) is not None

    job.schedule_cron = None
    db_session.commit()
    scheduler.reschedule_job(job, db_session)

    assert scheduler._scheduler.get_job(str(job.id)) is None
    db_session.expire_all()
    reloaded = db_session.query(Job).filter(Job.id == job.id).first()
    assert reloaded.is_enabled is True
    assert reloaded.next_run_at is None


def test_trigger_skips_when_job_already_running(db_session):
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    db_session.add(JobRun(job_id=job.id, trigger="schedule", status=JobRunStatus.running))
    db_session.commit()

    scheduler = JobScheduler()
    # Не должно бросать исключение — занятость задачи это штатный пропуск.
    scheduler.trigger_job(job.id, session_factory=lambda: db_session, close_session=False)

    assert db_session.query(JobRun).count() == 1
