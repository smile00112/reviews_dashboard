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
    ScrapeMode,
    ScrapeRunStatus,
)
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.models.review import Review
from app.services.metrics_service import PLATFORM_COLUMNS, MetricsOutcome, MetricsService
from app.services.scrape_service import ScrapeService

logger = logging.getLogger(__name__)

# Внутренние ключи площадок совпадают с ключами MetricsService.PLATFORM_COLUMNS.
PLATFORM_BY_ENUM: dict[ReviewPlatform, str] = {
    ReviewPlatform.yandex: "yandex",
    ReviewPlatform.gis2: "2gis",
}

_PLATFORM_ENUM_BY_KEY: dict[str, ReviewPlatform] = {v: k for k, v in PLATFORM_BY_ENUM.items()}

DEFAULT_DELAY_SECONDS = 2.0

_METRICS_ITEM_STATUS = {
    MetricsOutcome.updated: JobItemStatus.success,
    MetricsOutcome.failed: JobItemStatus.failed,
    MetricsOutcome.manual_action: JobItemStatus.needs_manual_action,
}

# Режим сбора отзывов по площадке. yandex -> public_http: единственный режим,
# который умеет ходить через пул прокси (Chromium не аутентифицируется в SOCKS5),
# а Yandex отдаёт 429 датацентровому IP задолго до конца полного сбора.
PLATFORM_SCRAPE_MODE: dict[str, ScrapeMode] = {
    "yandex": ScrapeMode.public_http,
    "2gis": ScrapeMode.twogis_api,
}

_SCRAPE_ITEM_STATUS = {
    ScrapeRunStatus.success: JobItemStatus.success,
    ScrapeRunStatus.failed: JobItemStatus.failed,
    ScrapeRunStatus.needs_manual_action: JobItemStatus.needs_manual_action,
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

    @property
    def scrape_service(self):
        if self._scrape_service is None:
            self._scrape_service = ScrapeService(self.db)
        return self._scrape_service

    # --- публичный вход ---

    def execute(self, run_id: UUID) -> None:
        run = self.db.query(JobRun).filter(JobRun.id == run_id).first()
        if run is None:
            return

        # Всё, что может тронуть БД для этого прогона — преамбула, выборка
        # организаций и сам обход — идёт под одним try/except: любое из этих
        # мест уже роняло run в незавершённое состояние (см. Finding 1), а
        # _finalize ниже гарантированно доводит run до терминального статуса
        # независимо от того, где именно случился сбой.
        statuses: list[JobItemStatus] = []
        crashed = False
        try:
            job = run.job
            platform = PLATFORM_BY_ENUM[job.platform]
            delay = float(job.options.get("delay_seconds", DEFAULT_DELAY_SECONDS))

            run.status = JobRunStatus.running
            job.last_run_at = datetime.now(timezone.utc)
            self.db.commit()

            orgs = self._select_organizations(platform)
            run.orgs_total = len(orgs)
            self.db.commit()

            for index, org in enumerate(orgs):
                if index:
                    self.sleep(delay)
                statuses.append(self._process_organization(run, job, org, platform))
        except Exception as exc:  # noqa: BLE001 — запуск не должен падать молча
            logger.exception("job run %s crashed", run_id)
            crashed = True
            # Откатываем незавершённую транзакцию первым делом: если этого не
            # сделать, _finalize().commit() падает с PendingRollbackError и
            # диагностика ниже никогда не долетает до БД.
            self.db.rollback()
            run.error_message = f"{type(exc).__name__}: {exc}"

        self._finalize(run, statuses, crashed=crashed)

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

        try:
            self.db.add(item)
            self.db.commit()
        except Exception as exc:  # noqa: BLE001 — сбой записи не должен ронять весь прогон
            logger.exception(
                "failed to persist job run item for organization %s in run %s", org.id, run.id
            )
            self.db.rollback()
            # Строку JobRunItem записать не удалось — диагностика уходит в
            # run.error_message, иначе она теряется безвозвратно.
            run.error_message = f"organization {org.id}: {type(exc).__name__}: {exc}"
            return JobItemStatus.failed
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
        """Собрать отзывы, только если счётчик площадки разошёлся с собранным.

        Расхождение -> полный проход по страницам: дедуп по content_hash сам
        отбросит уже известные отзывы, а счётчики ScrapeRun покажут прирост.
        """
        platform_enum = _PLATFORM_ENUM_BY_KEY[platform]
        count_col = PLATFORM_COLUMNS[platform][2]
        platform_total = getattr(org, count_col)
        scraped_before = (
            self.db.query(Review)
            .filter(Review.organization_id == org.id, Review.platform == platform_enum)
            .count()
        )
        payload = {"platform_total": platform_total, "scraped_before": scraped_before}

        if platform_total is None:
            return JobRunItem(
                job_run_id=run.id, organization_id=org.id, status=JobItemStatus.skipped,
                reason="счётчик площадки неизвестен — сначала нужен сбор метрик",
                payload=payload,
            )
        if platform_total <= scraped_before:
            return JobRunItem(
                job_run_id=run.id, organization_id=org.id, status=JobItemStatus.skipped,
                reason=f"счётчики совпадают: {platform_total} = {scraped_before}",
                payload=payload,
            )

        scrape_run = self.scrape_service.create_run(org.id, PLATFORM_SCRAPE_MODE[platform])
        self.scrape_service.execute_run(scrape_run.id)
        self.db.refresh(scrape_run)

        payload.update(
            {
                "reviews_seen": scrape_run.reviews_seen,
                "inserted": scrape_run.reviews_inserted,
                "updated": scrape_run.reviews_updated,
            }
        )
        return JobRunItem(
            job_run_id=run.id,
            organization_id=org.id,
            status=_SCRAPE_ITEM_STATUS.get(scrape_run.status, JobItemStatus.failed),
            payload=payload,
            scrape_run_id=scrape_run.id,
            error_code=scrape_run.error_code,
            error_message=scrape_run.error_message,
        )

    # --- финализация ---

    def _finalize(self, run: JobRun, statuses: list[JobItemStatus], *, crashed: bool = False) -> None:
        """Статус запуска по элементам: всё упало -> failed; ни одного успеха, но
        есть вызов оператора -> needs_manual_action; есть и успехи, и ошибки ->
        partial; иначе success.

        ``crashed`` переопределяет результат на failed: если сам прогон
        аварийно прервался, успехи организаций, обработанных до падения, не
        должны маскировать это как success/partial.
        """
        # statuses has one entry per organization that actually reached
        # _process_organization. After a mid-run crash (crashed=True) the loop
        # in execute() stops early, so orgs_total can exceed
        # orgs_succeeded + orgs_skipped + orgs_failed — the un-attempted
        # organizations never produced a status and are simply absent from
        # all three counters. That gap is expected; read it as "the run did
        # not reach every organization", not as a counting bug.
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

        if crashed:
            run.status = JobRunStatus.failed

        run.finished_at = datetime.now(timezone.utc)
        try:
            self.db.commit()
        except Exception as exc:  # noqa: BLE001 — финализация не должна ронять фоновую задачу
            logger.exception("failed to finalize job run %s", run.id)
            # Последняя попытка зафиксировать хоть что-то: откатываем половинчатую
            # транзакцию, ставим терминальный статус и ошибку, коммитим ещё раз.
            # Если и это не удаётся — глотаем исключение и логируем: фоновой
            # задаче бросать его дальше некуда.
            try:
                self.db.rollback()
                run.status = JobRunStatus.failed
                run.error_message = f"finalize failed: {type(exc).__name__}: {exc}"
                run.finished_at = datetime.now(timezone.utc)
                self.db.commit()
            except Exception:  # noqa: BLE001 — фону больше некуда бросать исключение
                logger.exception(
                    "failed to record terminal status for job run %s after finalize failure",
                    run.id,
                )
