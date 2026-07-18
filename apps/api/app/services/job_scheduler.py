"""In-process планировщик фоновых задач.

APScheduler внутри API-процесса — сознательно не очередь и не отдельный воркер
(конституция запрещает Celery/queues). Гонку двух реплик снимает блокировка
строки задачи в JobService.create_run, а не сам планировщик.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.models.enums import JobTrigger
from app.models.job import Job
from app.services.job_runner import JobRunner
from app.services.job_service import JobAlreadyRunning, JobService

logger = logging.getLogger(__name__)

RETENTION_JOB_ID = "job-run-retention"
# Очистка ночью, после всех сборов: они начинаются в 04:00 и 05:00.
RETENTION_CRON = "15 3 * * *"


def _default_session_factory() -> Session:
    from app.core.database import SessionLocal

    return SessionLocal()


class JobScheduler:
    def __init__(self) -> None:
        # coalesce: пропущенные из-за даунтайма срабатывания схлопываются в одно.
        # max_instances=1: одна задача не может идти в два потока.
        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
        )
        self._started = False

    # --- жизненный цикл ---

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        db = _default_session_factory()
        try:
            self.sync_all(db)
        finally:
            db.close()

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    # --- регистрация триггеров ---

    def sync_all(self, db: Session) -> None:
        self._scheduler.add_job(
            self.purge_old_runs,
            CronTrigger.from_crontab(RETENTION_CRON, timezone="Europe/Moscow"),
            id=RETENTION_JOB_ID,
            replace_existing=True,
        )
        for job in JobService(db).list_jobs():
            self._register(job, db)

    def reschedule_job(self, job: Job, db: Session) -> None:
        """Re-register one job's trigger after an edit.

        Takes the caller's session (the PATCH handler's request session) so
        `_register` commits `job.next_run_at` on the same session that holds
        the row, rather than an ORM-only assignment that a request-scoped
        session silently drops when it closes.
        """
        self._register(job, db)

    def _register(self, job: Job, db: Session) -> None:
        job_id = str(job.id)
        existing = self._scheduler.get_job(job_id)
        if not job.is_enabled or not job.schedule_cron:
            if existing:
                self._scheduler.remove_job(job_id)
            job.next_run_at = None
            db.commit()
            return

        trigger = CronTrigger.from_crontab(job.schedule_cron, timezone=job.timezone)
        scheduled = self._scheduler.add_job(
            self.trigger_job, trigger, args=[job.id], id=job_id, replace_existing=True
        )
        # add_job only computes next_run_time itself once the underlying
        # BackgroundScheduler is running (see _real_add_job); sync_all/_register
        # is also called before start() (tests call it directly, and start()
        # itself calls sync_all before the "started" flag flips), so the
        # attribute may not exist yet. Compute it the same way APScheduler
        # would so next_run_at is always accurate regardless of scheduler state.
        next_run_time = getattr(scheduled, "next_run_time", None)
        if next_run_time is None:
            next_run_time = trigger.get_next_fire_time(None, datetime.now(timezone.utc))
        job.next_run_at = next_run_time
        db.commit()

    # --- исполнение ---

    def trigger_job(self, job_id: UUID, session_factory=None, close_session: bool = True) -> None:
        db = (session_factory or _default_session_factory)()
        try:
            try:
                run = JobService(db).create_run(job_id, JobTrigger.schedule)
            except JobAlreadyRunning:
                # Предыдущий запуск ещё идёт — это штатный пропуск, не ошибка.
                logger.info("job %s is still running; scheduled tick skipped", job_id)
                return
            except LookupError:
                logger.warning("scheduled job %s no longer exists", job_id)
                return
            JobRunner(db).execute(run.id)
        finally:
            if close_session:
                db.close()

    def purge_old_runs(self) -> None:
        db = _default_session_factory()
        try:
            deleted = JobService(db).purge_old_runs(now=datetime.now(timezone.utc))
            logger.info("purged %s job runs past retention", deleted)
        finally:
            db.close()


scheduler = JobScheduler()
