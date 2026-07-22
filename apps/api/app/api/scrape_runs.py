from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import SessionLocal, get_db
from app.models.enums import ScrapeMode, ScrapeRunStatus
from app.models.organization import Organization
from app.schemas.scrape_run import (
    ScrapeRequest,
    ScrapeRunListResponse,
    ScrapeRunResponse,
    ScrapeStartResponse,
)
from app.services.organization_service import OrganizationService
from app.services.scrape_service import ScrapeService

router = APIRouter(tags=["scrape"])


def _run_scrape_background(run_id: UUID) -> None:
    db = SessionLocal()
    try:
        ScrapeService(db).execute_run(run_id)
    finally:
        db.close()


@router.post(
    "/api/organizations/{organization_id}/scrape",
    response_model=ScrapeStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def scrape_organization(
    organization_id: UUID,
    payload: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("action:scrape.run")),
) -> ScrapeStartResponse:
    org = OrganizationService(db).get(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    mode = payload.mode or org.preferred_scrape_mode
    service = ScrapeService(db)
    run = service.create_run(organization_id, mode)
    background_tasks.add_task(_run_scrape_background, run.id)
    return ScrapeStartResponse(scrape_run_id=run.id, status=ScrapeRunStatus.queued)


@router.post("/api/scrape/all", response_model=ScrapeStartResponse, status_code=status.HTTP_202_ACCEPTED)
def scrape_all(
    payload: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("action:scrape.run")),
) -> ScrapeStartResponse:
    mode = payload.mode or ScrapeMode.public
    org_count = db.query(Organization).count()
    service = ScrapeService(db)
    run = service.create_run(None, mode)
    background_tasks.add_task(_run_scrape_background, run.id)
    return ScrapeStartResponse(
        scrape_run_id=run.id,
        status=ScrapeRunStatus.queued,
        organization_count=org_count,
    )


@router.get("/api/scrape-runs", response_model=ScrapeRunListResponse)
def list_scrape_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    organization_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ScrapeRunListResponse:
    items = ScrapeService(db).list_runs(limit=limit, offset=offset, organization_id=organization_id)
    return ScrapeRunListResponse(items=items)


@router.get("/api/scrape-runs/{run_id}", response_model=ScrapeRunResponse)
def get_scrape_run(run_id: UUID, db: Session = Depends(get_db)) -> ScrapeRunResponse:
    run = ScrapeService(db).get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Scrape run not found")
    return run
