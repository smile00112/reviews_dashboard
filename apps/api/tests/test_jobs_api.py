from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

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


def test_patch_rejects_review_operator(operator_client, db_session):
    """A logged-in non-admin is authenticated (not 401) but still must not update jobs."""
    job = _seed_job(db_session)
    resp = operator_client.patch(f"/api/jobs/{job.id}", json={"is_enabled": True})
    assert resp.status_code == 403
    db_session.refresh(job)
    assert job.is_enabled is False


def test_run_now_rejects_review_operator(operator_client, db_session):
    job = _seed_job(db_session)
    with patch("app.api.jobs.run_job_background") as background:
        resp = operator_client.post(f"/api/jobs/{job.id}/run")
    assert resp.status_code == 403
    background.assert_not_called()
    assert db_session.query(JobRun).filter(JobRun.job_id == job.id).count() == 0


def test_admin_can_set_force_full_every_days(admin_client, db_session):
    job = _seed_job(db_session, kind=JobKind.reviews)
    resp = admin_client.patch(
        f"/api/jobs/{job.id}", json={"options": {"delay_seconds": 0, "force_full_every_days": 7}}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["options"]["force_full_every_days"] == 7


def test_invalid_force_full_every_days_is_422(admin_client, db_session):
    job = _seed_job(db_session, kind=JobKind.reviews)
    for bad in (0, -1, "weekly", True, 1.5):
        resp = admin_client.patch(f"/api/jobs/{job.id}", json={"options": {"force_full_every_days": bad}})
        assert resp.status_code == 422, f"{bad!r} must be rejected, got {resp.status_code}"


def test_admin_can_update_schedule(admin_client, db_session):
    job = _seed_job(db_session)
    resp = admin_client.patch(
        f"/api/jobs/{job.id}", json={"is_enabled": True, "schedule_cron": "*/15 * * * *"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["schedule_cron"] == "*/15 * * * *"
    assert resp.json()["is_enabled"] is True


def test_admin_update_persists_next_run_at_to_db(admin_client, db_session):
    """Regression: reschedule_job used to be handed a `db=None` scheduler
    session, so `job.next_run_at` was assigned on the ORM object but never
    committed — it looked correct in the response but was stale on the next
    GET /api/jobs. Read the row back through a fresh SELECT (not the
    in-memory `job` object) to prove the PATCH path actually persisted it."""
    job = _seed_job(db_session)
    resp = admin_client.patch(
        f"/api/jobs/{job.id}", json={"is_enabled": True, "schedule_cron": "*/15 * * * *"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["next_run_at"] is not None

    db_session.expire_all()
    reloaded = db_session.query(Job).filter(Job.id == job.id).first()
    assert reloaded.next_run_at is not None


def test_invalid_cron_is_rejected(admin_client, db_session):
    job = _seed_job(db_session)
    resp = admin_client.patch(f"/api/jobs/{job.id}", json={"schedule_cron": "не крон"})
    assert resp.status_code == 422


def test_manual_run_returns_202_and_conflicts_while_active(admin_client, db_session):
    job = _seed_job(db_session)
    with patch("app.api.jobs.run_job_background"):
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


def test_patch_unknown_job_returns_404(admin_client):
    resp = admin_client.patch(f"/api/jobs/{uuid4()}", json={"is_enabled": True})
    assert resp.status_code == 404


def test_run_now_unknown_job_returns_404(admin_client):
    with patch("app.api.jobs.run_job_background") as background:
        resp = admin_client.post(f"/api/jobs/{uuid4()}/run")
    assert resp.status_code == 404
    background.assert_not_called()


def test_list_job_runs_filters_by_since_until_and_paginates(client, db_session):
    job = _seed_job(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    runs = []
    for i in range(4):
        run = JobRun(
            job_id=job.id,
            trigger=JobTrigger.manual,
            status=JobRunStatus.success,
            started_at=base + timedelta(hours=i),
        )
        db_session.add(run)
        runs.append(run)
    db_session.commit()
    run1, run2, run3, run4 = runs

    # since/until narrows to the inclusive middle window, newest first.
    windowed = client.get(
        "/api/job-runs",
        params={
            "job_id": str(job.id),
            "since": (base + timedelta(hours=1)).isoformat(),
            "until": (base + timedelta(hours=2)).isoformat(),
        },
    )
    assert windowed.status_code == 200
    assert [item["id"] for item in windowed.json()["items"]] == [str(run3.id), str(run2.id)]

    # No filters: newest-first ordering across all four runs.
    all_resp = client.get("/api/job-runs", params={"job_id": str(job.id)})
    assert [item["id"] for item in all_resp.json()["items"]] == [
        str(run4.id),
        str(run3.id),
        str(run2.id),
        str(run1.id),
    ]

    # limit/offset paginate the same newest-first order.
    page1 = client.get("/api/job-runs", params={"job_id": str(job.id), "limit": 2, "offset": 0})
    assert [item["id"] for item in page1.json()["items"]] == [str(run4.id), str(run3.id)]

    page2 = client.get("/api/job-runs", params={"job_id": str(job.id), "limit": 2, "offset": 2})
    assert [item["id"] for item in page2.json()["items"]] == [str(run2.id), str(run1.id)]
