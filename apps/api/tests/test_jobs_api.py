from uuid import UUID

from app.models.enums import JobKind, JobRunStatus, JobTrigger, ReviewPlatform
from app.models.job import Job
from app.models.job_run import JobRun


def _seed_job(db_session, kind=JobKind.org_metrics, platform=ReviewPlatform.yandex):
    job = Job(kind=kind, platform=platform, schedule_cron="0 4 * * *", options={"delay_seconds": 0})
    db_session.add(job)
    db_session.commit()
    return job


def test_list_jobs_is_open_for_reading(client, db_session):
    _seed_job(db_session)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["kind"] == "org_metrics"
    assert body["items"][0]["platform"] == "yandex"
    assert body["items"][0]["last_run"] is None


def test_patch_requires_admin(client, db_session, seed_users):
    job = _seed_job(db_session)
    resp = client.patch(f"/api/jobs/{job.id}", json={"is_enabled": True})
    assert resp.status_code == 401


def test_admin_can_update_schedule(admin_client, db_session):
    job = _seed_job(db_session)
    resp = admin_client.patch(
        f"/api/jobs/{job.id}", json={"is_enabled": True, "schedule_cron": "*/15 * * * *"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["schedule_cron"] == "*/15 * * * *"
    assert resp.json()["is_enabled"] is True


def test_invalid_cron_is_rejected(admin_client, db_session):
    job = _seed_job(db_session)
    resp = admin_client.patch(f"/api/jobs/{job.id}", json={"schedule_cron": "не крон"})
    assert resp.status_code == 422


def test_manual_run_returns_202_and_conflicts_while_active(admin_client, db_session):
    job = _seed_job(db_session)
    resp = admin_client.post(f"/api/jobs/{job.id}/run")
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["job_run_id"]

    # JobRun.id is a postgresql-native UUID(as_uuid=True) column: on the SQLite
    # test backend its bind processor calls value.hex, which requires an actual
    # uuid.UUID instance rather than the plain string round-tripped through JSON.
    run = db_session.query(JobRun).filter(JobRun.id == UUID(run_id)).first()
    run.status = JobRunStatus.running
    db_session.commit()

    conflict = admin_client.post(f"/api/jobs/{job.id}/run")
    assert conflict.status_code == 409


def test_list_and_get_runs(client, db_session):
    job = _seed_job(db_session)
    run = JobRun(job_id=job.id, trigger=JobTrigger.manual, status=JobRunStatus.success)
    db_session.add(run)
    db_session.commit()

    listed = client.get("/api/job-runs", params={"job_id": str(job.id)})
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    detail = client.get(f"/api/job-runs/{run.id}")
    assert detail.status_code == 200
    assert detail.json()["items"] == []
    assert detail.json()["job"]["kind"] == "org_metrics"

    missing = client.get(f"/api/job-runs/{job.id}")
    assert missing.status_code == 404
