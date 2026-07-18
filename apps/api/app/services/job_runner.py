"""Исполнение одного запуска фоновой задачи.

Организации обходятся строго последовательно, с паузой между ними: площадки
режут частые запросы. Каждая организация даёт ровно один JobRunItem, поэтому
лог запуска отвечает на вопрос «что произошло с каждым филиалом».
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.enums import (
    JobItemStatus,
    JobKind,
    JobRunStatus,
    ReviewPlatform,
)
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.services.metrics_service import PLATFORM_COLUMNS, MetricsOutcome, MetricsService

logger = logging.getLogger(__name__)

# Внутренние ключи площадок совпадают с ключами MetricsService.PLATFORM_COLUMNS.
PLATFORM_BY_ENUM: dict[ReviewPlatform, str] = {
    ReviewPlatform.yandex: "yandex",
    ReviewPlatform.gis2: "2gis",
}

DEFAULT_DELAY_SECONDS = 2.0

_METRICS_ITEM_STATUS = {
    MetricsOutcome.updated: JobItemStatus.success,
    MetricsOutcome.failed: JobItemStatus.failed,
    MetricsOutcome.manual_action: JobItemStatus.needs_manual_action,
}


class JobRunner:
    def __init__(
        self,
        db: Session,
        metrics_service: MetricsService | None = None,
        scrape_service=None,
        sleep=time.sleep,
    ):
        self.db = db
        self._metrics_service = metrics_service
        self._scrape_service = scrape_service
        self.sleep = sleep

    @property
    def metrics_service(self) -> MetricsService:
        # Ленивое создание: конструктор скраперов не должен работать в запусках,
        # которым метрики не нужны.
        if self._metrics_service is None:
            self._metrics_service = MetricsService(self.db)
        return self._metrics_service

    # --- публичный вход ---

    def execute(self, run_id: UUID) -> None:
        run = self.db.query(JobRun).filter(JobRun.id == run_id).first()
        if run is None:
            return
        job = run.job
        platform = PLATFORM_BY_ENUM[job.platform]
        delay = float(job.options.get("delay_seconds", DEFAULT_DELAY_SECONDS))

        run.status = JobRunStatus.running
        job.last_run_at = datetime.now(timezone.utc)
        self.db.commit()

        orgs = self._select_organizations(platform)
        run.orgs_total = len(orgs)
        self.db.commit()

        statuses: list[JobItemStatus] = []
        try:
            for index, org in enumerate(orgs):
                if index:
                    self.sleep(delay)
                statuses.append(self._process_organization(run, job, org, platform))
        except Exception as exc:  # noqa: BLE001 — запуск не должен падать молча
            logger.exception("job run %s crashed", run_id)
            run.error_message = f"{type(exc).__name__}: {exc}"

        self._finalize(run, statuses)

    # --- обход организаций ---

    def _select_organizations(self, platform: str) -> list[Organization]:
        url_col = PLATFORM_COLUMNS[platform][0]
        column = getattr(Organization, url_col)
        return (
            self.db.query(Organization)
            .filter(column.isnot(None), column != "")
            .order_by(Organization.created_at, Organization.id)
            .all()
        )

    def _process_organization(self, run: JobRun, job, org: Organization, platform: str) -> JobItemStatus:
        started = time.monotonic()
        try:
            if job.kind is JobKind.org_metrics:
                item = self._run_metrics(run, org, platform)
            else:
                item = self._run_reviews(run, org, platform)
        except Exception as exc:  # noqa: BLE001 — одна организация не валит весь запуск
            logger.exception("organization %s failed in run %s", org.id, run.id)
            self.db.rollback()
            item = JobRunItem(
                job_run_id=run.id,
                organization_id=org.id,
                status=JobItemStatus.failed,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
        item.duration_ms = int((time.monotonic() - started) * 1000)
        self.db.add(item)
        self.db.commit()
        return item.status

    def _run_metrics(self, run: JobRun, org: Organization, platform: str) -> JobRunItem:
        result = self.metrics_service.refresh_organization(org, platform)
        return JobRunItem(
            job_run_id=run.id,
            organization_id=org.id,
            status=_METRICS_ITEM_STATUS[result.outcome],
            payload=result.payload,
            error_code=result.error_code,
        )

    def _run_reviews(self, run: JobRun, org: Organization, platform: str) -> JobRunItem:
        raise NotImplementedError  # Task 5

    # --- финализация ---

    def _finalize(self, run: JobRun, statuses: list[JobItemStatus]) -> None:
        """Статус запуска по элементам: всё упало -> failed; ни одного успеха, но
        есть вызов оператора -> needs_manual_action; есть и успехи, и ошибки ->
        partial; иначе success."""
        run.orgs_succeeded = sum(1 for s in statuses if s is JobItemStatus.success)
        run.orgs_skipped = sum(1 for s in statuses if s is JobItemStatus.skipped)
        run.orgs_failed = sum(
            1 for s in statuses if s in (JobItemStatus.failed, JobItemStatus.needs_manual_action)
        )

        has_success = JobItemStatus.success in statuses
        has_failure = any(s is JobItemStatus.failed for s in statuses)
        has_manual = any(s is JobItemStatus.needs_manual_action for s in statuses)

        if statuses and not has_success and not has_manual and has_failure:
            run.status = JobRunStatus.failed
        elif not has_success and has_manual:
            run.status = JobRunStatus.needs_manual_action
        elif has_success and (has_failure or has_manual):
            run.status = JobRunStatus.partial
        else:
            run.status = JobRunStatus.success

        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()
