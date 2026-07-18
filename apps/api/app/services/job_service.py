"""Чтение и правка фоновых задач, журнал их запусков, очистка старых логов."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, joinedload

from app.models.enums import JobRunStatus, JobTrigger
from app.models.job import Job
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem

# Логи запусков живут 20 дней; дальше их удаляет ночная очистка.
JOB_RUN_RETENTION_DAYS = 20

# Запуски, при которых задача считается занятой.
ACTIVE_RUN_STATUSES = (JobRunStatus.queued, JobRunStatus.running)

# Отличает «поле не передали» от «передали null»: null очищает расписание.
UNSET_CRON = object()


class JobAlreadyRunning(Exception):
    """У задачи уже есть запуск в статусе queued/running."""


class InvalidCron(Exception):
    """Строка расписания не разбирается как cron."""


def validate_cron(expression: str, timezone_name: str = "Europe/Moscow") -> None:
    try:
        CronTrigger.from_crontab(expression, timezone=timezone_name)
    except (ValueError, TypeError) as exc:
        raise InvalidCron(str(exc)) from exc


class JobService:
    def __init__(self, db: Session):
        self.db = db

    # --- задачи ---

    def list_jobs(self) -> list[Job]:
        return self.db.query(Job).order_by(Job.kind, Job.platform).all()

    def get_job(self, job_id: UUID) -> Job | None:
        return self.db.query(Job).filter(Job.id == job_id).first()

    def update_job(
        self,
        job_id: UUID,
        *,
        is_enabled: bool | None = None,
        schedule_cron: str | None = UNSET_CRON,  # type: ignore[assignment]
        options: dict | None = None,
    ) -> Job:
        job = self.get_job(job_id)
        if job is None:
            raise LookupError("Job not found")
        if schedule_cron is not UNSET_CRON:
            if schedule_cron:
                validate_cron(schedule_cron, job.timezone)
            job.schedule_cron = schedule_cron or None
        if is_enabled is not None:
            job.is_enabled = is_enabled
        if options is not None:
            job.options = options
        self.db.commit()
        self.db.refresh(job)
        return job

    # --- запуски ---

    def has_active_run(self, job_id: UUID) -> bool:
        return (
            self.db.query(JobRun)
            .filter(JobRun.job_id == job_id, JobRun.status.in_(ACTIVE_RUN_STATUSES))
            .first()
            is not None
        )

    def create_run(self, job_id: UUID, trigger: JobTrigger, user_id: UUID | None = None) -> JobRun:
        """Поставить запуск в очередь.

        Строка задачи блокируется на время проверки: без этого две реплики API
        (или ручной запуск, совпавший со срабатыванием cron) создали бы два
        параллельных запуска одной задачи. В SQLite with_for_update — no-op,
        это ожидаемо: тесты однопоточные.
        """
        job = self.db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if job is None:
            raise LookupError("Job not found")
        if self.has_active_run(job_id):
            raise JobAlreadyRunning(str(job_id))

        run = JobRun(job_id=job_id, trigger=trigger, triggered_by_user_id=user_id, status=JobRunStatus.queued)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(self, run_id: UUID) -> JobRun | None:
        return self.db.query(JobRun).filter(JobRun.id == run_id).first()

    def list_runs(
        self,
        *,
        job_id: UUID | None = None,
        status: JobRunStatus | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobRun]:
        query = self.db.query(JobRun)
        if job_id:
            query = query.filter(JobRun.job_id == job_id)
        if status:
            query = query.filter(JobRun.status == status)
        if since:
            query = query.filter(JobRun.started_at >= since)
        if until:
            query = query.filter(JobRun.started_at <= until)
        return query.order_by(JobRun.started_at.desc()).offset(offset).limit(limit).all()

    def list_run_items(self, run_id: UUID, *, limit: int = 200, offset: int = 0) -> list[JobRunItem]:
        return (
            self.db.query(JobRunItem)
            .options(joinedload(JobRunItem.organization))
            .filter(JobRunItem.job_run_id == run_id)
            .order_by(JobRunItem.id)
            .offset(offset)
            .limit(limit)
            .all()
        )

    # --- восстановление после рестарта ---

    def fail_interrupted_runs(self, now: datetime | None = None) -> int:
        """Пометить как failed все запуски, застрявшие в queued/running.

        Раннер живёт в процессе API (BackgroundTasks / APScheduler-поток), а не
        в отдельном воркере, так что запуск не переживает рестарт процесса.
        Прод деплоится на каждый push, так что зависший `running`/`queued`
        ряд — рутинная ситуация, а не редкий сбой: без починки он вечно
        блокирует и cron (has_active_run видит "занято"), и ручной запуск
        (create_run бросает JobAlreadyRunning) — до ручного SQL. Вызывается из
        lifespan ДО job_scheduler.start(), чтобы починка происходила независимо
        от того, включён ли флаг планировщика.
        """
        finished_at = now or datetime.now(timezone.utc)
        stale = (
            self.db.query(JobRun)
            .filter(JobRun.status.in_(ACTIVE_RUN_STATUSES))
            .all()
        )
        for run in stale:
            run.status = JobRunStatus.failed
            run.error_message = "interrupted by API restart"
            run.finished_at = finished_at
        self.db.commit()
        return len(stale)

    # --- retention ---

    def purge_old_runs(self, now: datetime | None = None) -> int:
        """Удалить запуски старше JOB_RUN_RETENTION_DAYS вместе с их элементами.

        Элементы удаляются явным bulk DELETE, а не через ORM-cascade на
        relationship: `JobRun.items` объявлен с `passive_deletes=True`,
        то есть SQLAlchemy рассчитывает на СУБД-уровневый ON DELETE CASCADE.
        В проде (Postgres) это сработало бы, но тестовый SQLite не включает
        `PRAGMA foreign_keys`, так что строки JobRunItem остались бы
        сиротами. Явное удаление корректно на обеих СУБД.
        """
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=JOB_RUN_RETENTION_DAYS)
        stale_ids = [row.id for row in self.db.query(JobRun.id).filter(JobRun.started_at < cutoff).all()]
        if not stale_ids:
            return 0
        self.db.query(JobRunItem).filter(JobRunItem.job_run_id.in_(stale_ids)).delete(synchronize_session=False)
        deleted = (
            self.db.query(JobRun)
            .filter(JobRun.id.in_(stale_ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
