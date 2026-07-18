from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import SessionLocal, get_db
from app.models.enums import JobRunStatus, JobTrigger
from app.schemas.job import (
    JobListResponse,
    JobResponse,
    JobRunDetailResponse,
    JobRunItemResponse,
    JobRunListResponse,
    JobRunResponse,
    JobRunStartResponse,
    JobUpdateRequest,
)
from app.services.job_runner import JobRunner
from app.services.job_service import UNSET_CRON, InvalidCron, JobAlreadyRunning, JobService

router = APIRouter(tags=["jobs"])


def run_job_background(run_id: UUID) -> None:
    """Фоновый запуск открывает собственную сессию — запросная уже закрыта."""
    db = SessionLocal()
    try:
        JobRunner(db).execute(run_id)
    finally:
        db.close()


def _job_response(service: JobService, job) -> JobResponse:
    latest = service.list_runs(job_id=job.id, limit=1)
    payload = JobResponse.model_validate(job)
    payload.last_run = latest[0] if latest else None
    return payload


@router.get("/api/jobs", response_model=JobListResponse)
def list_jobs(db: Session = Depends(get_db)) -> JobListResponse:
    service = JobService(db)
    return JobListResponse(items=[_job_response(service, job) for job in service.list_jobs()])


@router.patch("/api/jobs/{job_id}", response_model=JobResponse)
def update_job(
    job_id: UUID,
    payload: JobUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> JobResponse:
    service = JobService(db)
    fields = payload.model_dump(exclude_unset=True)
    try:
        job = service.update_job(
            job_id,
            is_enabled=fields.get("is_enabled"),
            schedule_cron=fields["schedule_cron"] if "schedule_cron" in fields else UNSET_CRON,
            options=fields.get("options"),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Job not found")
    except InvalidCron as exc:
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {exc}")

    from app.services.job_scheduler import scheduler

    scheduler.reschedule_job(job)
    return _job_response(service, job)


@router.post(
    "/api/jobs/{job_id}/run",
    response_model=JobRunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_job_now(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> JobRunStartResponse:
    service = JobService(db)
    try:
        run = service.create_run(job_id, JobTrigger.manual, user_id=admin.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Job not found")
    except JobAlreadyRunning:
        raise HTTPException(status_code=409, detail="Job is already running")

    background_tasks.add_task(run_job_background, run.id)
    return JobRunStartResponse(job_run_id=run.id, status=JobRunStatus.queued)


@router.get("/api/job-runs", response_model=JobRunListResponse)
def list_job_runs(
    job_id: UUID | None = None,
    run_status: JobRunStatus | None = Query(default=None, alias="status"),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobRunListResponse:
    items = JobService(db).list_runs(
        job_id=job_id, status=run_status, since=since, until=until, limit=limit, offset=offset
    )
    return JobRunListResponse(items=items)


@router.get("/api/job-runs/{run_id}", response_model=JobRunDetailResponse)
def get_job_run(
    run_id: UUID,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobRunDetailResponse:
    service = JobService(db)
    run = service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Job run not found")

    items = []
    for item in service.list_run_items(run_id, limit=limit, offset=offset):
        payload = JobRunItemResponse.model_validate(item)
        payload.organization_name = item.organization.name if item.organization else None
        items.append(payload)

    # Build from the scalar-only JobRunResponse rather than
    # JobRunDetailResponse.model_validate(run): the latter would eagerly
    # lazy-load the full unpaginated run.items (and run.job) only to have
    # both overwritten below by the paginated/enriched values.
    base = JobRunResponse.model_validate(run)
    return JobRunDetailResponse(
        **base.model_dump(),
        job=_job_response(service, run.job),
        items=items,
    )
