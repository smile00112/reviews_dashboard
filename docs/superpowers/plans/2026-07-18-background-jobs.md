# Background Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дашборд получает страницу `/jobs`, где оператор управляет четырьмя фоновыми задачами (сбор метрик и сбор отзывов × Яндекс и 2ГИС), запускает их вручную или по cron-расписанию и читает построчные логи каждого запуска.

**Architecture:** Три новые таблицы (`jobs` → `job_runs` → `job_run_items`) в текущем Postgres. `JobRunner` последовательно обходит организации и пишет по строке на каждую; метрики выполняет вынесенный из CLI `MetricsService`, отзывы — существующий `ScrapeService` (ссылка на `scrape_run_id` в логе). Расписание — in-process APScheduler, поднимаемый в FastAPI lifespan за фичефлагом. Существующая таблица `scrape_runs` не меняется.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, pydantic-settings, APScheduler 3.x, pytest + TestClient (SQLite in-memory), Next.js App Router + Tailwind, Playwright.

## Global Constraints

- Спецификация: `docs/superpowers/specs/2026-07-18-background-jobs-design.md`. Расхождение с ней — ошибка реализации.
- Никаких Celery/очередей/воркеров. Планировщик — только in-process APScheduler (конституция, «Out of scope»).
- Google не поддерживается. Площадки только `yandex` и `gis2`.
- Таблица `scrape_runs` и модель `ScrapeRun` не изменяются.
- Дедуп отзывов (`build_review_hash`) не трогается ни при каких обстоятельствах.
- Мутации (`PATCH /api/jobs/{id}`, `POST /api/jobs/{id}/run`) требуют `Depends(require_admin)`. GET-эндпоинты открыты — как остальной API.
- Retention: ровно 20 дней. Константа `JOB_RUN_RETENTION_DAYS = 20` объявляется один раз в `app/services/job_service.py` и импортируется везде, где нужна.
- Организации внутри запуска обрабатываются строго последовательно, с задержкой `options["delay_seconds"]` между организациями. Параллелизма нет.
- Тесты идут на SQLite in-memory (`conftest.py`), поэтому: JSONB объявляется как `JSON().with_variant(JSONB, "postgresql")`; `Enum(..., values_callable=lambda x: [e.value for e in x])`; `with_for_update()` в SQLite — no-op, это ожидаемо и допустимо.
- Каждая задача завершается коммитом. Сообщения коммитов на английском, тело — при неочевидном «почему».
- Проверочный гейт перед мержем: `pytest -v` в `apps/api`, затем `npm run lint && npm run test:e2e` в `apps/web`.

---

## File Structure

**Создаются (API):**
- `apps/api/app/models/job.py` — `Job`
- `apps/api/app/models/job_run.py` — `JobRun`
- `apps/api/app/models/job_run_item.py` — `JobRunItem`
- `apps/api/alembic/versions/0014_background_jobs.py` — таблицы, enum-типы, сиды 4 задач
- `apps/api/app/services/metrics_service.py` — `MetricsService` (логика из `scripts/scrape_metrics.py`)
- `apps/api/app/services/job_service.py` — чтение/правка задач, создание запусков, листинги, retention
- `apps/api/app/services/job_runner.py` — `JobRunner`, исполнение запуска
- `apps/api/app/services/job_scheduler.py` — обёртка над APScheduler
- `apps/api/app/schemas/job.py` — pydantic-схемы
- `apps/api/app/api/jobs.py` — роутер
- `apps/api/tests/test_metrics_service.py`, `test_job_service.py`, `test_job_runner_metrics.py`, `test_job_runner_reviews.py`, `test_jobs_api.py`, `test_job_scheduler.py`

**Изменяются (API):**
- `apps/api/app/models/enums.py` — 4 новых enum
- `apps/api/app/models/__init__.py` — регистрация моделей
- `apps/api/app/core/config.py` — `jobs_scheduler_enabled`
- `apps/api/app/main.py` — lifespan + роутер
- `apps/api/scripts/scrape_metrics.py` — становится тонкой обёрткой над `MetricsService`
- `apps/api/pyproject.toml` — зависимость `apscheduler`

**Создаются (Web):**
- `apps/web/app/(dashboard)/jobs/page.tsx`
- `apps/web/app/(dashboard)/jobs/runs/[id]/page.tsx`
- `apps/web/components/jobs/job-card.tsx`
- `apps/web/components/jobs/schedule-modal.tsx`
- `apps/web/components/jobs/job-runs-table.tsx`
- `apps/web/tests/jobs.spec.ts`

**Изменяются (Web):**
- `apps/web/lib/types.ts`, `apps/web/lib/api.ts`, `apps/web/components/shell/sidebar.tsx`

---

### Task 1: Модели, enum'ы и миграция

**Files:**
- Modify: `apps/api/app/models/enums.py`
- Create: `apps/api/app/models/job.py`, `apps/api/app/models/job_run.py`, `apps/api/app/models/job_run_item.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/alembic/versions/0014_background_jobs.py`
- Test: `apps/api/tests/test_job_models.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `JobKind.org_metrics|reviews`, `JobTrigger.schedule|manual`, `JobRunStatus.queued|running|success|partial|failed|needs_manual_action|cancelled`, `JobItemStatus.success|skipped|failed|needs_manual_action`; модели `Job`, `JobRun`, `JobRunItem` с полями по спеке; связи `JobRun.items` и `JobRun.job`.

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_job_models.py`:

```python
import uuid
from datetime import datetime, timezone

from app.models.enums import JobItemStatus, JobKind, JobRunStatus, JobTrigger, ReviewPlatform
from app.models.job import Job
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization


def test_job_run_item_cascades_and_defaults(db_session):
    job = Job(kind=JobKind.org_metrics, platform=ReviewPlatform.yandex, schedule_cron="0 4 * * *")
    db_session.add(job)
    db_session.commit()

    assert job.is_enabled is False
    assert job.options == {}
    assert job.timezone == "Europe/Moscow"

    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1")
    db_session.add(org)
    db_session.commit()

    run = JobRun(job_id=job.id, trigger=JobTrigger.manual, status=JobRunStatus.running)
    db_session.add(run)
    db_session.commit()
    assert run.orgs_total == 0

    item = JobRunItem(
        job_run_id=run.id,
        organization_id=org.id,
        status=JobItemStatus.skipped,
        reason="счётчики совпадают: 42 = 42",
        payload={"platform_total": 42, "scraped_before": 42},
    )
    db_session.add(item)
    db_session.commit()

    assert run.items[0].payload["platform_total"] == 42

    db_session.delete(run)
    db_session.commit()
    assert db_session.query(JobRunItem).count() == 0


def test_job_unique_per_kind_and_platform(db_session):
    from sqlalchemy.exc import IntegrityError

    db_session.add(Job(kind=JobKind.reviews, platform=ReviewPlatform.gis2))
    db_session.commit()
    db_session.add(Job(kind=JobKind.reviews, platform=ReviewPlatform.gis2))
    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:
        raise AssertionError("duplicate (kind, platform) must be rejected")
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_job_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.job'`

- [ ] **Step 3: Добавить enum'ы**

В конец `apps/api/app/models/enums.py`:

```python
class JobKind(str, enum.Enum):
    org_metrics = "org_metrics"
    reviews = "reviews"


class JobTrigger(str, enum.Enum):
    schedule = "schedule"
    manual = "manual"


class JobRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    success = "success"
    # Часть организаций отработала, часть упала — не failed и не success.
    partial = "partial"
    failed = "failed"
    needs_manual_action = "needs_manual_action"
    cancelled = "cancelled"


class JobItemStatus(str, enum.Enum):
    success = "success"
    skipped = "skipped"
    failed = "failed"
    needs_manual_action = "needs_manual_action"
```

- [ ] **Step 4: Написать модели**

`apps/api/app/models/job.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, JSON, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobKind, ReviewPlatform


class Job(Base):
    """Определение фоновой задачи. Ровно одна строка на (kind, platform)."""

    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("kind", "platform", name="uq_jobs_kind_platform"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[JobKind] = mapped_column(
        Enum(JobKind, name="job_kind_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    platform: Mapped[ReviewPlatform] = mapped_column(
        Enum(ReviewPlatform, name="review_platform_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/Moscow")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    runs = relationship("JobRun", back_populates="job", cascade="all, delete-orphan")
```

`apps/api/app/models/job_run.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobRunStatus, JobTrigger


class JobRun(Base):
    """Один запуск задачи — по расписанию или вручную."""

    __tablename__ = "job_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[JobTrigger] = mapped_column(
        Enum(JobTrigger, name="job_trigger_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[JobRunStatus] = mapped_column(
        Enum(JobRunStatus, name="job_run_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=JobRunStatus.queued,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orgs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("Job", back_populates="runs")
    items = relationship(
        "JobRunItem", back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
```

`apps/api/app/models/job_run_item.py`:

```python
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobItemStatus


class JobRunItem(Base):
    """Результат обработки одной организации внутри запуска.

    ``payload`` хранит «было → стало» в форме, зависящей от типа задачи:
      * org_metrics: rating_before/after, review_count_before/after, rating_count_before/after
      * reviews:     platform_total, scraped_before, reviews_seen, inserted, updated
    """

    __tablename__ = "job_run_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[JobItemStatus] = mapped_column(
        Enum(JobItemStatus, name="job_item_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    scrape_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run = relationship("JobRun", back_populates="items")
    organization = relationship("Organization")
```

Заменить `apps/api/app/models/__init__.py`:

```python
from app.models.company import Company
from app.models.job import Job
from app.models.job_run import JobRun
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.models.rating_snapshot import RatingSnapshot
from app.models.review import Review
from app.models.scrape_run import ScrapeRun
from app.models.scraper_session import ScraperSession
from app.models.user import User

__all__ = [
    "Company",
    "Job",
    "JobRun",
    "JobRunItem",
    "Organization",
    "RatingSnapshot",
    "Review",
    "ScrapeRun",
    "ScraperSession",
    "User",
]
```

- [ ] **Step 5: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_job_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Написать миграцию**

Создать `apps/api/alembic/versions/0014_background_jobs.py`:

```python
"""background jobs: jobs, job_runs, job_run_items

Revision ID: 0014_background_jobs
Revises: 0013_review_idx_session_pend
Create Date: 2026-07-18

Additive. Определения фоновых задач + журнал их запусков. Существующая
``scrape_runs`` не меняется: связь идёт через job_run_items.scrape_run_id.
Сидит 4 задачи (metrics/reviews × yandex/gis2), все выключенными — расписание
включает оператор.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_background_jobs"
down_revision: Union[str, None] = "0013_review_idx_session_pend"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

platform_enum = postgresql.ENUM(
    "yandex", "google", "gis2", name="review_platform_enum", create_type=False
)
job_kind_enum = postgresql.ENUM("org_metrics", "reviews", name="job_kind_enum")
job_trigger_enum = postgresql.ENUM("schedule", "manual", name="job_trigger_enum")
job_run_status_enum = postgresql.ENUM(
    "queued", "running", "success", "partial", "failed", "needs_manual_action", "cancelled",
    name="job_run_status_enum",
)
job_item_status_enum = postgresql.ENUM(
    "success", "skipped", "failed", "needs_manual_action", name="job_item_status_enum"
)


def upgrade() -> None:
    bind = op.get_bind()
    job_kind_enum.create(bind, checkfirst=True)
    job_trigger_enum.create(bind, checkfirst=True)
    job_run_status_enum.create(bind, checkfirst=True)
    job_item_status_enum.create(bind, checkfirst=True)

    jobs = op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", job_kind_enum, nullable=False),
        sa.Column("platform", platform_enum, nullable=False),
        sa.Column("schedule_cron", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="Europe/Moscow"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("kind", "platform", name="uq_jobs_kind_platform"),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("trigger", job_trigger_enum, nullable=False),
        sa.Column(
            "triggered_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("status", job_run_status_enum, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orgs_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_index("ix_job_runs_job_started", "job_runs", ["job_id", sa.text("started_at DESC")])

    op.create_table(
        "job_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_run_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("status", job_item_status_enum, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "scrape_run_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_job_run_items_job_run_id", "job_run_items", ["job_run_id"])

    # Сиды: метрики в 04:00, отзывы в 05:00 — отзывам нужен свежий review_count.
    op.bulk_insert(
        jobs,
        [
            {
                "id": uuid.uuid4(), "kind": kind, "platform": platform,
                "schedule_cron": cron, "timezone": "Europe/Moscow",
                "is_enabled": False, "options": {"delay_seconds": 2},
            }
            for kind, cron in (("org_metrics", "0 4 * * *"), ("reviews", "0 5 * * *"))
            for platform in ("yandex", "gis2")
        ],
    )


def downgrade() -> None:
    op.drop_table("job_run_items")
    op.drop_table("job_runs")
    op.drop_table("jobs")
    bind = op.get_bind()
    job_item_status_enum.drop(bind, checkfirst=True)
    job_run_status_enum.drop(bind, checkfirst=True)
    job_trigger_enum.drop(bind, checkfirst=True)
    job_kind_enum.drop(bind, checkfirst=True)
```

- [ ] **Step 7: Проверить, что цепочка миграций имеет одну голову**

Run: `cd apps/api && alembic heads`
Expected: одна строка — `0014_background_jobs (head)`

- [ ] **Step 8: Прогнать весь тестовый набор**

Run: `cd apps/api && pytest -v`
Expected: PASS, регрессий нет

- [ ] **Step 9: Коммит**

```bash
git add apps/api/app/models apps/api/alembic/versions/0014_background_jobs.py apps/api/tests/test_job_models.py
git commit -m "feat(api): jobs, job_runs and job_run_items tables"
```

---

### Task 2: MetricsService — вынести логику метрик из CLI

**Files:**
- Create: `apps/api/app/services/metrics_service.py`
- Modify: `apps/api/scripts/scrape_metrics.py`
- Test: `apps/api/tests/test_metrics_service.py`

**Interfaces:**
- Consumes: ничего из Task 1.
- Produces:
  - `PLATFORM_COLUMNS: dict[str, tuple[str, str, str, str, str, str]]` — платформа → `(url_attr, rating_col, review_count_col, rating_count_col, status_col, success_ts_col)`; ключи `"yandex"` и `"2gis"`.
  - `class MetricsOutcome(str, enum.Enum)`: `updated | failed | manual_action`.
  - `@dataclass MetricsResult`: `outcome: MetricsOutcome`, `payload: dict`, `error_code: str | None`.
  - `class MetricsService`: `__init__(self, db: Session, scrapers: Scrapers | None = None)`; `refresh_organization(self, org: Organization, platform: str) -> MetricsResult` — скрапит метрики и пишет их на строку организации, **без** `commit()` (коммитит вызывающий).
  - `class Scrapers` переезжает в этот модуль (метод `scrape(platform: str, url: str) -> ScrapeResult` не меняется).

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_metrics_service.py`:

```python
from decimal import Decimal

from app.models.enums import OrganizationScrapeStatus
from app.models.organization import Organization
from app.scraper.types import ParsedOrganization, ScrapeResult
from app.services.metrics_service import MetricsOutcome, MetricsService


class FakeScrapers:
    def __init__(self, result: ScrapeResult):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def scrape(self, platform: str, url: str) -> ScrapeResult:
        self.calls.append((platform, url))
        return self.result


def _result(rating=None, review_count=None, rating_count=None, error_code=None, manual=False):
    return ScrapeResult(
        organization=ParsedOrganization(
            rating=rating, review_count=review_count, rating_count=rating_count
        ),
        reviews=[],
        needs_manual_action=manual,
        error_code=error_code,
    )


def test_refresh_writes_yandex_columns(db_session):
    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1", rating=Decimal("4.0"))
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(4.7, 120, 340)))
    result = service.refresh_organization(org, "yandex")
    db_session.commit()

    assert result.outcome is MetricsOutcome.updated
    assert float(org.rating) == 4.7
    assert org.review_count == 120
    assert org.yandex_rating_count == 340
    assert org.yandex_scrape_status == OrganizationScrapeStatus.success
    assert org.yandex_last_successful_scrape_at is not None
    assert result.payload["rating_before"] == 4.0
    assert result.payload["rating_after"] == 4.7


def test_refresh_never_wipes_known_value_on_failure(db_session):
    org = Organization(name="Org", yandex_url="https://yandex.ru/maps/org/1", rating=Decimal("4.2"), review_count=99)
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(rating=None, error_code="http_500")))
    result = service.refresh_organization(org, "yandex")
    db_session.commit()

    assert result.outcome is MetricsOutcome.failed
    assert result.error_code == "http_500"
    assert float(org.rating) == 4.2
    assert org.review_count == 99
    assert org.yandex_scrape_status == OrganizationScrapeStatus.failed


def test_refresh_marks_manual_action(db_session):
    org = Organization(name="Org", gis2_url="https://2gis.ru/firm/1")
    db_session.add(org)
    db_session.commit()

    service = MetricsService(db_session, scrapers=FakeScrapers(_result(manual=True)))
    result = service.refresh_organization(org, "2gis")
    db_session.commit()

    assert result.outcome is MetricsOutcome.manual_action
    assert org.gis2_scrape_status == OrganizationScrapeStatus.needs_manual_action
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_metrics_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.metrics_service'`

- [ ] **Step 3: Написать сервис**

Создать `apps/api/app/services/metrics_service.py`:

```python
"""Сбор метрик организации (рейтинг, число отзывов, число оценок).

Логика жила в scripts/scrape_metrics.py; вынесена в сервис, чтобы фоновая
задача и CLI использовали одну реализацию. Отдельные отзывы не читаются —
скраперы вызываются с metrics_only=True.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.enums import OrganizationScrapeStatus
from app.models.organization import Organization
from app.scraper.twogis_api import TwogisApiScraper
from app.scraper.types import ScrapeResult
from app.scraper.yandex_http import YandexHttpScraper
from app.scraper.yandex_scrapeops import YandexScrapeOpsScraper

# платформа -> (url, rating, review_count, rating_count, status, success-ts)
PLATFORM_COLUMNS: dict[str, tuple[str, str, str, str, str, str]] = {
    "yandex": (
        "yandex_url", "rating", "review_count", "yandex_rating_count",
        "yandex_scrape_status", "yandex_last_successful_scrape_at",
    ),
    "2gis": (
        "gis2_url", "gis2_rating", "gis2_review_count", "gis2_rating_count",
        "gis2_scrape_status", "gis2_last_successful_scrape_at",
    ),
}


class MetricsOutcome(str, enum.Enum):
    updated = "updated"
    failed = "failed"
    manual_action = "manual_action"


@dataclass
class MetricsResult:
    outcome: MetricsOutcome
    payload: dict = field(default_factory=dict)
    error_code: str | None = None


class Scrapers:
    """Лениво создаваемые скраперы, переиспользуемые в пределах прогона."""

    def __init__(self) -> None:
        self.yandex_http = YandexHttpScraper()
        self.yandex_proxy = YandexScrapeOpsScraper()
        self.twogis = TwogisApiScraper()

    def scrape(self, platform: str, url: str) -> ScrapeResult:
        if platform == "2gis":
            return self.twogis.scrape(url, metrics_only=True)
        # yandex: сначала browserless, затем ScrapeOps как фолбэк — на вызов
        # оператора, ошибку или пустой рейтинг.
        result = self.yandex_http.scrape(url, metrics_only=True)
        if result.needs_manual_action or result.error_code or result.organization.rating is None:
            fallback = self.yandex_proxy.scrape(url)
            if not (fallback.needs_manual_action or fallback.error_code) and fallback.organization.rating is not None:
                return fallback
        return result


def _as_float(value) -> float | None:
    return None if value is None else float(value)


class MetricsService:
    def __init__(self, db: Session, scrapers: Scrapers | None = None):
        self.db = db
        self.scrapers = scrapers or Scrapers()

    def refresh_organization(self, org: Organization, platform: str) -> MetricsResult:
        """Обновить метрики организации для одной площадки.

        Никогда не затирает известное значение пустым: скрап без рейтинга —
        это провал, а не повод обнулить цифру. Не коммитит: транзакцией
        управляет вызывающий.
        """
        url_col, rating_col, count_col, rating_count_col, status_col, ts_col = PLATFORM_COLUMNS[platform]
        url = getattr(org, url_col)
        payload = {
            "rating_before": _as_float(getattr(org, rating_col)),
            "review_count_before": getattr(org, count_col),
            "rating_count_before": getattr(org, rating_count_col),
        }

        result = self.scrapers.scrape(platform, url)

        if result.needs_manual_action:
            setattr(org, status_col, OrganizationScrapeStatus.needs_manual_action)
            return MetricsResult(MetricsOutcome.manual_action, payload, result.error_code)

        if result.error_code or result.organization.rating is None:
            setattr(org, status_col, OrganizationScrapeStatus.failed)
            return MetricsResult(MetricsOutcome.failed, payload, result.error_code or "no_rating")

        setattr(org, rating_col, result.organization.rating)
        if result.organization.review_count is not None:
            setattr(org, count_col, result.organization.review_count)
        if result.organization.rating_count is not None:
            setattr(org, rating_count_col, result.organization.rating_count)
        setattr(org, status_col, OrganizationScrapeStatus.success)
        setattr(org, ts_col, datetime.now(timezone.utc))

        payload.update(
            {
                "rating_after": _as_float(getattr(org, rating_col)),
                "review_count_after": getattr(org, count_col),
                "rating_count_after": getattr(org, rating_count_col),
            }
        )
        return MetricsResult(MetricsOutcome.updated, payload)
```

- [ ] **Step 4: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_metrics_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Переключить CLI на сервис**

В `apps/api/scripts/scrape_metrics.py` удалить классы `Scrapers` (строки 89–107) и функцию `apply_result` (строки 120–149), удалить константу `PLATFORMS` (строки 34–43) и неиспользуемые импорты скраперов; вместо них:

```python
from app.services.metrics_service import (
    PLATFORM_COLUMNS as PLATFORMS,
    MetricsOutcome,
    MetricsService,
    Scrapers,
)
```

В `run(...)` заменить вызов `scrapers.scrape(...)` + `apply_result(...)` на сервис. Сигнатура `run()` не меняется — вместо `scrapers: Scrapers` теперь используется `MetricsService`, создаваемый внутри:

```python
    service = MetricsService(session, scrapers=scrapers)
    ...
            result = service.refresh_organization(org, platform)
            outcome = result.outcome.value if result.outcome is not MetricsOutcome.manual_action else "manual_action"
            if result.outcome is MetricsOutcome.updated:
                psummary.updated += 1
                detail = (
                    f" rating={result.payload['rating_after']}"
                    f" rating_count={result.payload['rating_count_after']}"
                    f" review_count={result.payload['review_count_after']}"
                )
            elif result.outcome is MetricsOutcome.manual_action:
                psummary.manual_action += 1
                detail = f" ({result.error_code or 'no rating'})"
            else:
                psummary.failed += 1
                detail = f" ({result.error_code or 'no rating'})"
            logger.log(f"  [{idx}/{len(orgs)}] [{platform}] {label}: {outcome}{detail}")
```

- [ ] **Step 6: Проверить, что CLI не сломан**

Run: `cd apps/api && python -m scripts.scrape_metrics --platform yandex --limit 1 --dry-run`
Expected: скрипт стартует, печатает строку `start platforms=yandex ...` и завершается кодом 0 (сетевой сбой в выводе допустим — проверяется, что импорты и связка целы).

- [ ] **Step 7: Прогнать весь набор тестов**

Run: `cd apps/api && pytest -v`
Expected: PASS

- [ ] **Step 8: Коммит**

```bash
git add apps/api/app/services/metrics_service.py apps/api/scripts/scrape_metrics.py apps/api/tests/test_metrics_service.py
git commit -m "refactor(api): extract MetricsService from the metrics CLI

The background metrics job and the operator CLI must share one
implementation; two copies would drift."
```

---

### Task 3: JobService — задачи, запуски, листинги, retention

**Files:**
- Create: `apps/api/app/services/job_service.py`
- Test: `apps/api/tests/test_job_service.py`

**Interfaces:**
- Consumes: `Job`, `JobRun`, `JobRunItem`, `JobKind`, `JobRunStatus`, `JobTrigger` (Task 1).
- Produces: `JOB_RUN_RETENTION_DAYS = 20`; `ACTIVE_RUN_STATUSES = (JobRunStatus.queued, JobRunStatus.running)`; сентинел `UNSET_CRON`; `class JobAlreadyRunning(Exception)`; `class InvalidCron(Exception)`; `class JobService` с методами:
  - `list_jobs() -> list[Job]`
  - `get_job(job_id: UUID) -> Job | None`
  - `update_job(job_id, *, is_enabled=None, schedule_cron=..., options=None) -> Job` (валидирует cron, поднимает `InvalidCron`)
  - `create_run(job_id: UUID, trigger: JobTrigger, user_id: UUID | None = None) -> JobRun` (поднимает `JobAlreadyRunning`)
  - `list_runs(*, job_id=None, status=None, since=None, until=None, limit=50, offset=0) -> list[JobRun]`
  - `get_run(run_id: UUID) -> JobRun | None`
  - `list_run_items(run_id: UUID, *, limit=200, offset=0) -> list[JobRunItem]`
  - `purge_old_runs(now: datetime | None = None) -> int`

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_job_service.py`:

```python
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
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_job_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.job_service'`

- [ ] **Step 3: Добавить зависимость APScheduler**

В `apps/api/pyproject.toml`, в список `dependencies`, добавить строку:

```toml
    "apscheduler>=3.10,<4",
```

Установить:

Run: `cd apps/api && pip install -e ".[dev]"`
Expected: `Successfully installed ... apscheduler-3.x`

- [ ] **Step 4: Написать сервис**

Создать `apps/api/app/services/job_service.py`:

```python
"""Чтение и правка фоновых задач, журнал их запусков, очистка старых логов."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

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
            .filter(JobRunItem.job_run_id == run_id)
            .order_by(JobRunItem.id)
            .offset(offset)
            .limit(limit)
            .all()
        )

    # --- retention ---

    def purge_old_runs(self, now: datetime | None = None) -> int:
        """Удалить запуски старше JOB_RUN_RETENTION_DAYS. Элементы уходят каскадом."""
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=JOB_RUN_RETENTION_DAYS)
        stale = self.db.query(JobRun).filter(JobRun.started_at < cutoff).all()
        for run in stale:
            self.db.delete(run)
        self.db.commit()
        return len(stale)
```

- [ ] **Step 5: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_job_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Коммит**

```bash
git add apps/api/app/services/job_service.py apps/api/tests/test_job_service.py apps/api/pyproject.toml
git commit -m "feat(api): JobService with run guard, filters and 20-day retention"
```

---

### Task 4: JobRunner — задача сбора метрик

**Files:**
- Create: `apps/api/app/services/job_runner.py`
- Test: `apps/api/tests/test_job_runner_metrics.py`

**Interfaces:**
- Consumes: `JobService`, `MetricsService`/`MetricsOutcome`/`PLATFORM_COLUMNS`, модели из Task 1.
- Produces:
  - `PLATFORM_BY_ENUM: dict[ReviewPlatform, str]` — `{ReviewPlatform.yandex: "yandex", ReviewPlatform.gis2: "2gis"}`.
  - `class JobRunner`: `__init__(self, db: Session, metrics_service: MetricsService | None = None, scrape_service: ScrapeService | None = None, sleep=time.sleep)`; `execute(self, run_id: UUID) -> None`.
  - `JobRunner._select_organizations(self, platform: str) -> list[Organization]` — организации с непустым URL площадки, порядок `created_at, id`.

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_job_runner_metrics.py`:

```python
import pytest

from app.models.enums import (
    JobItemStatus,
    JobKind,
    JobRunStatus,
    JobTrigger,
    ReviewPlatform,
)
from app.models.job import Job
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.services.job_service import JobService
from app.services.job_runner import JobRunner
from app.services.metrics_service import MetricsOutcome, MetricsResult


class FakeMetricsService:
    """Отдаёт заранее заданные исходы по порядку обхода организаций."""

    def __init__(self, outcomes: list[MetricsResult]):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def refresh_organization(self, org, platform):
        self.calls.append((org.name, platform))
        return self.outcomes.pop(0)


@pytest.fixture()
def metrics_job(db_session):
    job = Job(kind=JobKind.org_metrics, platform=ReviewPlatform.yandex, options={"delay_seconds": 0})
    db_session.add(job)
    db_session.commit()
    return job


def _orgs(db_session, count: int, *, yandex=True):
    orgs = []
    for i in range(count):
        org = Organization(
            name=f"Org {i}",
            yandex_url=f"https://yandex.ru/maps/org/{i}" if yandex else None,
        )
        db_session.add(org)
        orgs.append(org)
    db_session.commit()
    return orgs


def test_metrics_run_writes_one_item_per_organization(db_session, metrics_job):
    _orgs(db_session, 2)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.updated, {"rating_after": 4.7}),
        MetricsResult(MetricsOutcome.failed, {}, "http_500"),
    ])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    items = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).all()
    assert len(items) == 2
    assert {i.status for i in items} == {JobItemStatus.success, JobItemStatus.failed}
    assert run.status is JobRunStatus.partial
    assert (run.orgs_total, run.orgs_succeeded, run.orgs_failed) == (2, 1, 1)
    assert run.finished_at is not None


def test_metrics_run_all_failed_marks_run_failed(db_session, metrics_job):
    _orgs(db_session, 2)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.failed, {}, "http_500"),
        MetricsResult(MetricsOutcome.failed, {}, "http_500"),
    ])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    assert run.status is JobRunStatus.failed


def test_metrics_run_manual_action_without_success(db_session, metrics_job):
    _orgs(db_session, 1)
    fake = FakeMetricsService([MetricsResult(MetricsOutcome.manual_action, {}, "captcha")])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    assert run.status is JobRunStatus.needs_manual_action


def test_metrics_run_without_organizations_is_success(db_session, metrics_job):
    _orgs(db_session, 1, yandex=False)  # нет yandex_url — организация вне выборки
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=FakeMetricsService([]), sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    assert run.status is JobRunStatus.success
    assert run.orgs_total == 0
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_job_runner_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.job_runner'`

- [ ] **Step 3: Написать раннер (ветка метрик)**

Создать `apps/api/app/services/job_runner.py`:

```python
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
```

- [ ] **Step 4: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_job_runner_metrics.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Коммит**

```bash
git add apps/api/app/services/job_runner.py apps/api/tests/test_job_runner_metrics.py
git commit -m "feat(api): JobRunner executes the org-metrics job"
```

---

### Task 5: JobRunner — задача сбора отзывов со сравнением счётчиков

**Files:**
- Modify: `apps/api/app/services/job_runner.py`
- Test: `apps/api/tests/test_job_runner_reviews.py`

**Interfaces:**
- Consumes: `JobRunner` (Task 4), `ScrapeService.create_run/execute_run`, `ScrapeMode`.
- Produces: `PLATFORM_SCRAPE_MODE: dict[str, ScrapeMode]` — `{"yandex": ScrapeMode.public_http, "2gis": ScrapeMode.twogis_api}`; рабочая реализация `JobRunner._run_reviews`.

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_job_runner_reviews.py`:

```python
import uuid

import pytest

from app.models.enums import (
    JobItemStatus,
    JobKind,
    JobRunStatus,
    JobTrigger,
    ReviewPlatform,
    ScrapeMode,
    ScrapeRunStatus,
)
from app.models.job import Job
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.models.review import Review
from app.models.scrape_run import ScrapeRun
from app.services.job_runner import JobRunner
from app.services.job_service import JobService


class FakeScrapeService:
    """Пишет ScrapeRun как настоящий сервис, но ничего не скрапит."""

    def __init__(self, db, inserted=3, status=ScrapeRunStatus.success):
        self.db = db
        self.inserted = inserted
        self.status = status
        self.executed: list[uuid.UUID] = []

    def create_run(self, organization_id, mode):
        run = ScrapeRun(organization_id=organization_id, mode=mode, status=ScrapeRunStatus.queued)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def execute_run(self, run_id, limit=None, max_pages=None):
        self.executed.append(run_id)
        run = self.db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
        run.status = self.status
        run.reviews_seen = self.inserted
        run.reviews_inserted = self.inserted
        run.reviews_updated = 0
        self.db.commit()


@pytest.fixture()
def reviews_job(db_session):
    job = Job(kind=JobKind.reviews, platform=ReviewPlatform.yandex, options={"delay_seconds": 0})
    db_session.add(job)
    db_session.commit()
    return job


def _org(db_session, *, review_count):
    org = Organization(
        name="Org", yandex_url="https://yandex.ru/maps/org/1", review_count=review_count
    )
    db_session.add(org)
    db_session.commit()
    return org


def _seed_reviews(db_session, org, count):
    for i in range(count):
        db_session.add(
            Review(
                organization_id=org.id,
                platform=ReviewPlatform.yandex,
                content_hash=f"hash-{i}",
                author_name="A",
                rating=5,
                review_text="text",
            )
        )
    db_session.commit()


def test_skips_when_counts_match(db_session, reviews_job):
    org = _org(db_session, review_count=2)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.skipped
    assert "2" in item.reason
    assert item.scrape_run_id is None
    assert scrape.executed == []
    db_session.refresh(run)
    assert run.status is JobRunStatus.success
    assert run.orgs_skipped == 1


def test_skips_when_platform_count_unknown(db_session, reviews_job):
    _org(db_session, review_count=None)
    scrape = FakeScrapeService(db_session)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.skipped
    assert scrape.executed == []


def test_scrapes_when_counts_differ_and_links_scrape_run(db_session, reviews_job):
    org = _org(db_session, review_count=5)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session, inserted=3)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.success
    assert item.scrape_run_id is not None
    assert item.payload["platform_total"] == 5
    assert item.payload["scraped_before"] == 2
    assert item.payload["inserted"] == 3
    assert len(scrape.executed) == 1

    linked = db_session.query(ScrapeRun).filter(ScrapeRun.id == item.scrape_run_id).one()
    assert linked.mode is ScrapeMode.public_http


def test_failed_scrape_run_marks_item_failed(db_session, reviews_job):
    org = _org(db_session, review_count=5)
    _seed_reviews(db_session, org, 2)
    scrape = FakeScrapeService(db_session, inserted=0, status=ScrapeRunStatus.failed)
    run = JobService(db_session).create_run(reviews_job.id, JobTrigger.manual)

    JobRunner(db_session, scrape_service=scrape, sleep=lambda _s: None).execute(run.id)

    item = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).one()
    assert item.status is JobItemStatus.failed
    db_session.refresh(run)
    assert run.status is JobRunStatus.failed
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_job_runner_reviews.py -v`
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Реализовать ветку отзывов**

В `apps/api/app/services/job_runner.py` добавить импорты:

```python
from app.models.enums import ScrapeMode, ScrapeRunStatus
from app.models.review import Review
from app.services.scrape_service import ScrapeService
```

Добавить константы рядом с `PLATFORM_BY_ENUM`:

```python
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
```

Добавить ленивое свойство рядом с `metrics_service`:

```python
    @property
    def scrape_service(self):
        if self._scrape_service is None:
            self._scrape_service = ScrapeService(self.db)
        return self._scrape_service
```

Заменить заглушку `_run_reviews`:

```python
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
```

Добавить обратную карту рядом с `PLATFORM_BY_ENUM`:

```python
_PLATFORM_ENUM_BY_KEY: dict[str, ReviewPlatform] = {v: k for k, v in PLATFORM_BY_ENUM.items()}
```

- [ ] **Step 4: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_job_runner_reviews.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Прогнать весь набор**

Run: `cd apps/api && pytest -v`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add apps/api/app/services/job_runner.py apps/api/tests/test_job_runner_reviews.py
git commit -m "feat(api): reviews job scrapes only when platform count diverges"
```

---

### Task 6: API — схемы и роутер

**Files:**
- Create: `apps/api/app/schemas/job.py`, `apps/api/app/api/jobs.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_jobs_api.py`

**Interfaces:**
- Consumes: `JobService`, `JobRunner`, `JobAlreadyRunning`, `InvalidCron`.
- Produces: HTTP-контракт `GET /api/jobs`, `PATCH /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/run`, `GET /api/job-runs`, `GET /api/job-runs/{run_id}`; схемы `JobResponse`, `JobListResponse`, `JobUpdateRequest`, `JobRunResponse`, `JobRunListResponse`, `JobRunItemResponse`, `JobRunDetailResponse`, `JobRunStartResponse`.

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_jobs_api.py`:

```python
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

    run = db_session.query(JobRun).filter(JobRun.id == run_id).first()
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
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_jobs_api.py -v`
Expected: FAIL — все запросы возвращают 404 (роутера нет)

- [ ] **Step 3: Написать схемы**

Создать `apps/api/app/schemas/job.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobItemStatus, JobKind, JobRunStatus, JobTrigger, ReviewPlatform


class JobRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    trigger: JobTrigger
    triggered_by_user_id: UUID | None
    status: JobRunStatus
    started_at: datetime
    finished_at: datetime | None
    orgs_total: int
    orgs_succeeded: int
    orgs_skipped: int
    orgs_failed: int
    error_message: str | None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: JobKind
    platform: ReviewPlatform
    schedule_cron: str | None
    timezone: str
    is_enabled: bool
    options: dict
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_run: JobRunResponse | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]


class JobUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    schedule_cron: str | None = None
    options: dict | None = None


class JobRunStartResponse(BaseModel):
    job_run_id: UUID
    status: JobRunStatus


class JobRunItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    status: JobItemStatus
    reason: str | None
    payload: dict
    scrape_run_id: UUID | None
    error_code: str | None
    error_message: str | None
    duration_ms: int | None


class JobRunListResponse(BaseModel):
    items: list[JobRunResponse]


class JobRunDetailResponse(JobRunResponse):
    job: JobResponse
    items: list[JobRunItemResponse] = Field(default_factory=list)
```

- [ ] **Step 4: Написать роутер**

Создать `apps/api/app/api/jobs.py`:

```python
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

    detail = JobRunDetailResponse.model_validate(run)
    detail.job = _job_response(service, run.job)
    detail.items = items
    return detail
```

Роутер импортирует сентинел `UNSET_CRON` из сервиса — он отличает «поле не пришло» от «пришло null» (null очищает расписание). В `apps/api/app/services/job_service.py` переименовать приватный `_UNSET = object()` в публичный:

```python
# Отличает «поле не передали» от «передали null»: null очищает расписание.
UNSET_CRON = object()
```

и в сигнатуре `JobService.update_job` заменить `schedule_cron: str | None = _UNSET` на `schedule_cron: str | None = UNSET_CRON`, а проверку `if schedule_cron is not _UNSET:` — на `if schedule_cron is not UNSET_CRON:`.

- [ ] **Step 5: Зарегистрировать роутер**

В `apps/api/app/main.py` заменить строку импорта роутеров:

```python
from app.api import auth, companies, dashboard, jobs, organizations, reviews, scrape_runs, scraper_sessions
```

и добавить после `app.include_router(dashboard.router)`:

```python
app.include_router(jobs.router)
```

- [ ] **Step 6: Добавить заглушку планировщика, чтобы роутер импортировался**

Создать `apps/api/app/services/job_scheduler.py` с минимальным API (полная реализация — Task 7):

```python
"""Заглушка планировщика: реальная реализация появляется в следующей задаче."""


class _NullScheduler:
    def reschedule_job(self, job) -> None:
        return None


scheduler = _NullScheduler()
```

- [ ] **Step 7: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_jobs_api.py -v`
Expected: PASS (6 passed)

- [ ] **Step 8: Коммит**

```bash
git add apps/api/app/schemas/job.py apps/api/app/api/jobs.py apps/api/app/services/job_scheduler.py apps/api/app/services/job_service.py apps/api/app/main.py apps/api/tests/test_jobs_api.py
git commit -m "feat(api): /api/jobs and /api/job-runs endpoints"
```

---

### Task 7: Планировщик APScheduler и ночная очистка логов

**Files:**
- Modify: `apps/api/app/services/job_scheduler.py` (заменить заглушку)
- Modify: `apps/api/app/core/config.py`, `apps/api/app/main.py`
- Test: `apps/api/tests/test_job_scheduler.py`

**Interfaces:**
- Consumes: `JobService`, `JobRunner`, `JobAlreadyRunning`, `JOB_RUN_RETENTION_DAYS`.
- Produces: `settings.jobs_scheduler_enabled: bool`; `class JobScheduler` с `start()`, `shutdown()`, `reschedule_job(job)`, `sync_all()`, `trigger_job(job_id: UUID)`; синглтон `scheduler = JobScheduler()`; `RETENTION_JOB_ID = "job-run-retention"`.

- [ ] **Step 1: Написать падающий тест**

Создать `apps/api/tests/test_job_scheduler.py`:

```python
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
    scheduler.reschedule_job(job)

    assert scheduler._scheduler.get_job(str(job.id)) is None


def test_next_run_at_is_written_back(db_session):
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    scheduler = JobScheduler()
    scheduler.sync_all(db_session)
    db_session.refresh(job)
    assert job.next_run_at is not None


def test_trigger_skips_when_job_already_running(db_session):
    job = _job(db_session, cron="0 4 * * *", enabled=True)
    db_session.add(JobRun(job_id=job.id, trigger="schedule", status=JobRunStatus.running))
    db_session.commit()

    scheduler = JobScheduler()
    # Не должно бросать исключение — занятость задачи это штатный пропуск.
    scheduler.trigger_job(job.id, session_factory=lambda: db_session, close_session=False)

    assert db_session.query(JobRun).count() == 1
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd apps/api && pytest tests/test_job_scheduler.py -v`
Expected: FAIL — `ImportError: cannot import name 'JobScheduler'`

- [ ] **Step 3: Добавить настройку**

В `apps/api/app/core/config.py`, перед `settings = Settings()`, добавить:

```python
    # Фоновые задачи (feature: background jobs). Планировщик живёт внутри
    # API-процесса — никаких очередей. В тестах и CLI выключен, иначе прогон
    # pytest начал бы ходить на площадки.
    jobs_scheduler_enabled: bool = True
```

- [ ] **Step 4: Написать планировщик**

Заменить содержимое `apps/api/app/services/job_scheduler.py`:

```python
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

    def reschedule_job(self, job: Job) -> None:
        self._register(job, None)

    def _register(self, job: Job, db: Session | None) -> None:
        job_id = str(job.id)
        existing = self._scheduler.get_job(job_id)
        if not job.is_enabled or not job.schedule_cron:
            if existing:
                self._scheduler.remove_job(job_id)
            job.next_run_at = None
            if db is not None:
                db.commit()
            return

        trigger = CronTrigger.from_crontab(job.schedule_cron, timezone=job.timezone)
        scheduled = self._scheduler.add_job(
            self.trigger_job, trigger, args=[job.id], id=job_id, replace_existing=True
        )
        job.next_run_at = scheduled.next_run_time
        if db is not None:
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
```

- [ ] **Step 5: Поднять планировщик в lifespan**

В `apps/api/app/main.py` добавить импорты:

```python
from contextlib import asynccontextmanager

from app.services.job_scheduler import scheduler as job_scheduler
```

и заменить создание приложения:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.jobs_scheduler_enabled:
        job_scheduler.start()
    try:
        yield
    finally:
        job_scheduler.shutdown()


app = FastAPI(title="Yandex Reviews API", version="0.1.0", lifespan=lifespan)
```

- [ ] **Step 6: Выключить планировщик в тестах**

В `apps/api/tests/conftest.py`, рядом со строкой `os.environ.setdefault("ADMIN_SECRET_KEY", ...)`, добавить:

```python
# TestClient проходит через lifespan; без флага прогон тестов поднял бы
# планировщик и начал ходить на площадки.
os.environ.setdefault("JOBS_SCHEDULER_ENABLED", "false")
```

- [ ] **Step 7: Запустить тест — он должен пройти**

Run: `cd apps/api && pytest tests/test_job_scheduler.py -v`
Expected: PASS (4 passed)

- [ ] **Step 8: Прогнать весь набор**

Run: `cd apps/api && pytest -v`
Expected: PASS

- [ ] **Step 9: Задокументировать флаг**

В `.env.example` (корень репозитория) добавить строку:

```
JOBS_SCHEDULER_ENABLED=true
```

- [ ] **Step 10: Коммит**

```bash
git add apps/api/app/services/job_scheduler.py apps/api/app/core/config.py apps/api/app/main.py apps/api/tests/conftest.py apps/api/tests/test_job_scheduler.py .env.example
git commit -m "feat(api): in-process APScheduler for background jobs

Cron triggers plus a nightly retention sweep, behind
JOBS_SCHEDULER_ENABLED so pytest and CLI runs never scrape."
```

---

### Task 8: Веб-клиент — типы и API-функции

**Files:**
- Modify: `apps/web/lib/types.ts`, `apps/web/lib/api.ts`

**Interfaces:**
- Consumes: HTTP-контракт из Task 6.
- Produces: типы `JobKind`, `JobTrigger`, `JobRunStatus`, `JobItemStatus`, `Job`, `JobRun`, `JobRunItem`, `JobRunDetail`; функции `listJobs()`, `updateJob(id, payload)`, `runJobNow(id)`, `listJobRuns(params)`, `getJobRun(id)`.

- [ ] **Step 1: Добавить типы**

В конец `apps/web/lib/types.ts`:

```ts
// --- Фоновые задачи ---
export type JobKind = "org_metrics" | "reviews";

export type JobTrigger = "schedule" | "manual";

export type JobRunStatus =
  | "queued"
  | "running"
  | "success"
  | "partial"
  | "failed"
  | "needs_manual_action"
  | "cancelled";

export type JobItemStatus = "success" | "skipped" | "failed" | "needs_manual_action";

export interface JobRun {
  id: string;
  job_id: string;
  trigger: JobTrigger;
  triggered_by_user_id: string | null;
  status: JobRunStatus;
  started_at: string;
  finished_at: string | null;
  orgs_total: number;
  orgs_succeeded: number;
  orgs_skipped: number;
  orgs_failed: number;
  error_message: string | null;
}

export interface Job {
  id: string;
  kind: JobKind;
  platform: "yandex" | "gis2";
  schedule_cron: string | null;
  timezone: string;
  is_enabled: boolean;
  options: Record<string, unknown>;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run: JobRun | null;
}

export interface JobRunItem {
  id: string;
  organization_id: string;
  organization_name: string | null;
  status: JobItemStatus;
  reason: string | null;
  payload: Record<string, number | string | null>;
  scrape_run_id: string | null;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number | null;
}

export interface JobRunDetail extends JobRun {
  job: Job;
  items: JobRunItem[];
}
```

- [ ] **Step 2: Добавить API-функции**

В `apps/web/lib/api.ts` расширить импорт типов (`Job`, `JobRun`, `JobRunDetail`, `JobRunStatus`) и добавить в конец файла:

```ts
// --- Фоновые задачи ---
export async function listJobs(): Promise<Job[]> {
  const data = await request<{ items: Job[] }>("/api/jobs");
  return data.items;
}

export async function updateJob(
  id: string,
  payload: { is_enabled?: boolean; schedule_cron?: string | null; options?: Record<string, unknown> },
): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function runJobNow(id: string): Promise<{ job_run_id: string; status: JobRunStatus }> {
  return request<{ job_run_id: string; status: JobRunStatus }>(`/api/jobs/${id}/run`, {
    method: "POST",
  });
}

export async function listJobRuns(params: {
  job_id?: string;
  status?: JobRunStatus;
  since?: string;
  limit?: number;
} = {}): Promise<JobRun[]> {
  const query = new URLSearchParams();
  if (params.job_id) query.set("job_id", params.job_id);
  if (params.status) query.set("status", params.status);
  if (params.since) query.set("since", params.since);
  query.set("limit", String(params.limit ?? 50));
  const data = await request<{ items: JobRun[] }>(`/api/job-runs?${query.toString()}`);
  return data.items;
}

export async function getJobRun(id: string): Promise<JobRunDetail> {
  return request<JobRunDetail>(`/api/job-runs/${id}`);
}
```

- [ ] **Step 3: Проверить типы и линт**

Run: `cd apps/web && npm run lint`
Expected: PASS, ошибок нет

- [ ] **Step 4: Коммит**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts
git commit -m "feat(web): API client for background jobs"
```

---

### Task 9: Страница `/jobs` — карточки задач и таблица запусков

**Files:**
- Create: `apps/web/app/(dashboard)/jobs/page.tsx`, `apps/web/components/jobs/job-card.tsx`, `apps/web/components/jobs/schedule-modal.tsx`, `apps/web/components/jobs/job-runs-table.tsx`
- Modify: `apps/web/components/shell/sidebar.tsx`

**Interfaces:**
- Consumes: `listJobs`, `updateJob`, `runJobNow`, `listJobRuns` (Task 8).
- Produces: `JOB_LABELS: Record<JobKind, string>`, `PLATFORM_LABELS`, `describeCron(cron: string | null): string`, `jobStatusClass(status: JobRunStatus): string` — экспортируются из `components/jobs/job-card.tsx` и переиспользуются деталкой (Task 10).

- [ ] **Step 1: Написать карточку задачи**

Создать `apps/web/components/jobs/job-card.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { Job, JobKind, JobRunStatus } from "@/lib/types";
import { ScheduleModal } from "./schedule-modal";

export const JOB_LABELS: Record<JobKind, string> = {
  org_metrics: "Данные организаций",
  reviews: "Отзывы",
};

export const PLATFORM_LABELS: Record<Job["platform"], string> = {
  yandex: "Яндекс",
  gis2: "2ГИС",
};

export function jobStatusClass(status: JobRunStatus): string {
  if (status === "success") return "bg-green-100 text-green-800";
  if (status === "partial") return "bg-amber-100 text-amber-900";
  if (status === "failed") return "bg-red-100 text-red-800";
  if (status === "needs_manual_action") return "bg-amber-200 text-amber-950 ring-1 ring-amber-400";
  if (status === "running" || status === "queued") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
}

/** Человекочитаемое расписание для частых форм; иначе — сырой cron. */
export function describeCron(cron: string | null): string {
  if (!cron) return "не задано";
  const daily = cron.match(/^(\d{1,2}) (\d{1,2}) \* \* \*$/);
  if (daily) return `ежедневно в ${daily[2].padStart(2, "0")}:${daily[1].padStart(2, "0")}`;
  const everyHours = cron.match(/^0 \*\/(\d{1,2}) \* \* \*$/);
  if (everyHours) return `каждые ${everyHours[1]} ч`;
  if (cron === "0 * * * *") return "каждый час";
  return cron;
}

interface JobCardProps {
  job: Job;
  onChanged: () => void;
  onToggle: (job: Job, enabled: boolean) => Promise<void>;
  onRun: (job: Job) => Promise<void>;
  onSchedule: (job: Job, cron: string) => Promise<void>;
  error: string | null;
}

export function JobCard({ job, onToggle, onRun, onSchedule, error }: JobCardProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const running = job.last_run?.status === "running" || job.last_run?.status === "queued";

  async function guarded(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4" data-testid="job-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">
            {JOB_LABELS[job.kind]} — {PLATFORM_LABELS[job.platform]}
          </div>
          <div className="mt-1 text-xs text-text-dim">{describeCron(job.schedule_cron)}</div>
        </div>
        <label className="flex items-center gap-2 text-xs text-text-dim">
          <input
            type="checkbox"
            checked={job.is_enabled}
            disabled={busy}
            onChange={(e) => guarded(() => onToggle(job, e.target.checked))}
          />
          вкл
        </label>
      </div>

      <div className="mt-3 text-xs">
        {job.last_run ? (
          <span className={`rounded px-2 py-0.5 font-medium ${jobStatusClass(job.last_run.status)}`}>
            {job.last_run.status}
          </span>
        ) : (
          <span className="text-text-faint">ещё не запускалась</span>
        )}
        {job.last_run_at && (
          <span className="ml-2 text-text-dim">{new Date(job.last_run_at).toLocaleString("ru-RU")}</span>
        )}
      </div>

      {error && <div className="mt-2 text-xs text-red-700">{error}</div>}

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className="rounded border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          disabled={busy || running}
          onClick={() => guarded(() => onRun(job))}
          data-testid="job-run-now"
        >
          Запустить сейчас
        </button>
        <button
          type="button"
          className="rounded border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          disabled={busy}
          onClick={() => setModalOpen(true)}
        >
          Изменить расписание
        </button>
      </div>

      {modalOpen && (
        <ScheduleModal
          job={job}
          onClose={() => setModalOpen(false)}
          onSubmit={async (cron) => {
            await guarded(() => onSchedule(job, cron));
            setModalOpen(false);
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Написать модалку расписания**

Создать `apps/web/components/jobs/schedule-modal.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { Job } from "@/lib/types";

const PRESETS: { label: string; cron: string }[] = [
  { label: "Каждый час", cron: "0 * * * *" },
  { label: "Каждые 6 часов", cron: "0 */6 * * *" },
  { label: "Ежедневно в 04:00", cron: "0 4 * * *" },
  { label: "Ежедневно в 05:00", cron: "0 5 * * *" },
];

interface ScheduleModalProps {
  job: Job;
  onClose: () => void;
  onSubmit: (cron: string) => Promise<void>;
}

export function ScheduleModal({ job, onClose, onSubmit }: ScheduleModalProps) {
  const [cron, setCron] = useState(job.schedule_cron ?? "0 4 * * *");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-4">
        <div className="font-medium">Расписание</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.cron}
              type="button"
              className={`rounded border px-2 py-1 text-xs ${
                cron === preset.cron ? "border-accent text-accent" : "border-border"
              }`}
              onClick={() => setCron(preset.cron)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <label className="mt-3 block text-xs text-text-dim">
          Cron ({job.timezone})
          <input
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1 font-mono text-xs"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            data-testid="cron-input"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="rounded border border-border px-3 py-1.5 text-xs" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-black"
            onClick={() => onSubmit(cron)}
            data-testid="cron-save"
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Написать таблицу запусков**

Создать `apps/web/components/jobs/job-runs-table.tsx`:

```tsx
import Link from "next/link";
import type { Job, JobRun } from "@/lib/types";
import { JOB_LABELS, PLATFORM_LABELS, jobStatusClass } from "./job-card";

function duration(run: JobRun) {
  if (!run.finished_at) return "—";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return `${Math.round(ms / 1000)}s`;
}

interface JobRunsTableProps {
  runs: JobRun[];
  jobs: Job[];
}

export function JobRunsTable({ runs, jobs }: JobRunsTableProps) {
  const byId = new Map(jobs.map((job) => [job.id, job]));

  if (runs.length === 0) {
    return <p className="text-sm text-text-dim">Запусков пока нет.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full text-sm">
        <thead className="bg-surface-2 text-left text-text-dim">
          <tr>
            <th className="px-3 py-2">Задача</th>
            <th className="px-3 py-2">Триггер</th>
            <th className="px-3 py-2">Начало</th>
            <th className="px-3 py-2">Длительность</th>
            <th className="px-3 py-2">Статус</th>
            <th className="px-3 py-2">Успешно / пропущено / ошибки</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const job = byId.get(run.job_id);
            return (
              <tr key={run.id} className="border-t border-border" data-testid="job-run-row">
                <td className="px-3 py-2">
                  {job ? `${JOB_LABELS[job.kind]} — ${PLATFORM_LABELS[job.platform]}` : "—"}
                </td>
                <td className="px-3 py-2">{run.trigger === "manual" ? "вручную" : "по расписанию"}</td>
                <td className="px-3 py-2">{new Date(run.started_at).toLocaleString("ru-RU")}</td>
                <td className="px-3 py-2">{duration(run)}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${jobStatusClass(run.status)}`}>
                    {run.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {run.orgs_succeeded} / {run.orgs_skipped} / {run.orgs_failed}
                </td>
                <td className="px-3 py-2 text-xs">
                  <Link className="text-accent" href={`/jobs/runs/${run.id}`}>
                    подробнее
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Написать страницу**

Создать `apps/web/app/(dashboard)/jobs/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listJobRuns, listJobs, runJobNow, updateJob } from "@/lib/api";
import type { Job, JobRun, JobRunStatus } from "@/lib/types";
import { JobCard } from "@/components/jobs/job-card";
import { JobRunsTable } from "@/components/jobs/job-runs-table";

const STATUS_FILTERS: (JobRunStatus | "")[] = [
  "",
  "success",
  "partial",
  "failed",
  "needs_manual_action",
  "running",
];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [jobFilter, setJobFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<JobRunStatus | "">("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const filters = useRef({ jobFilter, statusFilter });
  filters.current = { jobFilter, statusFilter };

  const refresh = useCallback(async () => {
    const { jobFilter: job_id, statusFilter: status } = filters.current;
    const [nextJobs, nextRuns] = await Promise.all([
      listJobs(),
      listJobRuns({ job_id: job_id || undefined, status: status || undefined }),
    ]);
    setJobs(nextJobs);
    setRuns(nextRuns);
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
  }, [refresh, jobFilter, statusFilter]);

  // Опрос только пока что-то выполняется: в покое страница не дёргает API.
  useEffect(() => {
    const active = runs.some((run) => run.status === "running" || run.status === "queued");
    if (!active) return;
    const timer = setInterval(() => refresh().catch(console.error), 5000);
    return () => clearInterval(timer);
  }, [runs, refresh]);

  function setError(jobId: string, message: string | null) {
    setErrors((prev) => {
      const next = { ...prev };
      if (message) next[jobId] = message;
      else delete next[jobId];
      return next;
    });
  }

  async function act(job: Job, action: () => Promise<unknown>) {
    setError(job.id, null);
    try {
      await action();
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        job.id,
        status === 409
          ? "Задача уже выполняется"
          : status === 401 || status === 403
            ? "Нужны права администратора"
            : (err as Error).message,
      );
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Фоновые задачи</h1>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {jobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            error={errors[job.id] ?? null}
            onChanged={refresh}
            onToggle={(target, enabled) =>
              act(target, () => updateJob(target.id, { is_enabled: enabled }))
            }
            onRun={(target) => act(target, () => runJobNow(target.id))}
            onSchedule={(target, cron) =>
              act(target, () => updateJob(target.id, { schedule_cron: cron }))
            }
          />
        ))}
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">Запуски</h2>
          <select
            className="rounded border border-border bg-transparent px-2 py-1 text-xs"
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            data-testid="job-filter"
          >
            <option value="">все задачи</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>
                {job.kind} / {job.platform}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-border bg-transparent px-2 py-1 text-xs"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as JobRunStatus | "")}
            data-testid="status-filter"
          >
            {STATUS_FILTERS.map((value) => (
              <option key={value} value={value}>
                {value || "все статусы"}
              </option>
            ))}
          </select>
        </div>
        <JobRunsTable runs={runs} jobs={jobs} />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Добавить пункт в сайдбар**

В `apps/web/components/shell/sidebar.tsx`, в группу «Аналитика», после строки `/scrape-runs`:

```tsx
      { href: "/jobs", label: "Фоновые задачи", icon: "⏱" },
```

- [ ] **Step 6: Проверить линт и глазами**

Run: `cd apps/web && npm run lint`
Expected: PASS

Затем: поднять стек (`docker compose up` или `npm run dev` + `uvicorn`), открыть `http://localhost:3000/jobs`.
Expected: 4 карточки, у каждой расписание «ежедневно в 04:00»/«ежедневно в 05:00» и подпись «ещё не запускалась»; таблица показывает «Запусков пока нет.»

- [ ] **Step 7: Коммит**

```bash
git add apps/web/app/\(dashboard\)/jobs apps/web/components/jobs apps/web/components/shell/sidebar.tsx
git commit -m "feat(web): background jobs page with cards, filters and polling"
```

---

### Task 10: Деталь запуска, E2E-тест и документация

**Files:**
- Create: `apps/web/app/(dashboard)/jobs/runs/[id]/page.tsx`, `apps/web/tests/jobs.spec.ts`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `getJobRun` (Task 8), `JOB_LABELS`/`PLATFORM_LABELS`/`jobStatusClass` (Task 9).
- Produces: конечный пользовательский поток; ничего для последующих задач.

- [ ] **Step 1: Написать страницу детали**

Создать `apps/web/app/(dashboard)/jobs/runs/[id]/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { getJobRun } from "@/lib/api";
import type { JobRunDetail } from "@/lib/types";
import { JOB_LABELS, PLATFORM_LABELS, jobStatusClass } from "@/components/jobs/job-card";

const ITEM_STATUS_LABELS: Record<string, string> = {
  success: "успешно",
  skipped: "пропущено",
  failed: "ошибка",
  needs_manual_action: "нужен оператор",
};

function formatPayload(payload: Record<string, number | string | null>): string {
  const entries = Object.entries(payload).filter(([, value]) => value !== null && value !== undefined);
  if (entries.length === 0) return "—";
  return entries.map(([key, value]) => `${key}=${value}`).join(", ");
}

export default function JobRunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [run, setRun] = useState<JobRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobRun(id)
      .then(setRun)
      .catch((err: Error) => setError(err.message));
  }, [id]);

  // Пока запуск идёт — обновляем; закончился — перестаём опрашивать.
  useEffect(() => {
    if (!run || (run.status !== "running" && run.status !== "queued")) return;
    const timer = setInterval(() => {
      getJobRun(id).then(setRun).catch(console.error);
    }, 5000);
    return () => clearInterval(timer);
  }, [run, id]);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!run) return <p className="text-sm text-text-dim">Загрузка…</p>;

  return (
    <div className="space-y-4">
      <Link className="text-xs text-accent" href="/jobs">
        ← к задачам
      </Link>
      <h1 className="text-2xl font-semibold">
        {JOB_LABELS[run.job.kind]} — {PLATFORM_LABELS[run.job.platform]}
      </h1>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${jobStatusClass(run.status)}`}>
          {run.status}
        </span>
        <span className="text-text-dim">{new Date(run.started_at).toLocaleString("ru-RU")}</span>
        <span className="text-text-dim">
          организаций: {run.orgs_total} · успешно {run.orgs_succeeded} · пропущено {run.orgs_skipped} · ошибок{" "}
          {run.orgs_failed}
        </span>
      </div>
      {run.error_message && <p className="text-sm text-red-700">{run.error_message}</p>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-2 text-left text-text-dim">
            <tr>
              <th className="px-3 py-2">Организация</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2">Детали</th>
              <th className="px-3 py-2">Причина / ошибка</th>
              <th className="px-3 py-2">Сбор</th>
            </tr>
          </thead>
          <tbody>
            {run.items.map((item) => (
              <tr key={item.id} className="border-t border-border align-top" data-testid="job-run-item">
                <td className="px-3 py-2">{item.organization_name ?? item.organization_id}</td>
                <td className="px-3 py-2">{ITEM_STATUS_LABELS[item.status] ?? item.status}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatPayload(item.payload)}</td>
                <td className="max-w-xs px-3 py-2 text-xs">
                  {item.reason ?? item.error_message ?? "—"}
                </td>
                <td className="px-3 py-2 text-xs">{item.scrape_run_id ? "есть" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.items.length === 0 && <p className="text-sm text-text-dim">Строк по организациям нет.</p>}
    </div>
  );
}
```

- [ ] **Step 2: Написать E2E-тест**

Создать `apps/web/tests/jobs.spec.ts` (структуру логина/базового URL взять из существующего `apps/web/tests/reviews.spec.ts` — использовать те же хелперы и `test.describe`):

```ts
import { expect, test } from "@playwright/test";

test.describe("Фоновые задачи", () => {
  test("страница показывает четыре задачи", async ({ page }) => {
    await page.goto("/jobs");
    await expect(page.getByRole("heading", { name: "Фоновые задачи" })).toBeVisible();
    await expect(page.getByTestId("job-card")).toHaveCount(4);
  });

  test("фильтр запусков доступен и не роняет страницу", async ({ page }) => {
    await page.goto("/jobs");
    await page.getByTestId("status-filter").selectOption("failed");
    await expect(page.getByRole("heading", { name: "Запуски" })).toBeVisible();
  });

  test("ручной запуск создаёт строку в таблице запусков", async ({ page }) => {
    await page.goto("/jobs");
    const runButton = page.getByTestId("job-run-now").first();
    await runButton.click();
    await expect(page.getByTestId("job-run-row").first()).toBeVisible({ timeout: 15000 });
  });

  test("деталь запуска открывается", async ({ page }) => {
    await page.goto("/jobs");
    const link = page.getByRole("link", { name: "подробнее" }).first();
    await link.click();
    await expect(page.getByRole("link", { name: "← к задачам" })).toBeVisible();
  });
});
```

- [ ] **Step 3: Прогнать E2E**

Run (при поднятых API и web): `cd apps/web && npm run test:e2e -- tests/jobs.spec.ts`
Expected: PASS (4 passed)

Если тест ручного запуска падает 401/403 — логин админом должен выполняться так же, как в `tests/reviews.spec.ts`; добавить тот же `beforeEach`-логин.

- [ ] **Step 4: Обновить CLAUDE.md**

В `CLAUDE.md`, в раздел «Architecture», после подраздела про scrape flow, добавить:

```markdown
### Background jobs (страница `/jobs`)
Четыре задачи `kind × platform` (`org_metrics`/`reviews` × `yandex`/`gis2`) в таблице `jobs`, по одной строке на комбинацию. Запуск — вручную (`POST /api/jobs/{id}/run`, admin) или по cron: in-process APScheduler поднимается в FastAPI lifespan за флагом `JOBS_SCHEDULER_ENABLED` (в pytest и CLI = false). `JobRunner` идёт по организациям последовательно с задержкой `options.delay_seconds` и пишет по `JobRunItem` на организацию; статус запуска агрегируется (all-failed → `failed`, без успехов но с manual → `needs_manual_action`, смесь → `partial`, иначе `success`). Задача `reviews` скрапит организацию, только если `Organization.<platform>_review_count` больше числа собранных `reviews` — иначе `skipped` с причиной. Метрики выполняет `MetricsService` (общий с `scripts/scrape_metrics.py`). Логи (`job_runs` + `job_run_items`) живут 20 дней, чистит ночной внутренний триггер 03:15. `scrape_runs` не изменяется — связь через `job_run_items.scrape_run_id`.
```

В разделе «Commands», в блок про API, добавить строку про миграцию — не требуется отдельно, `alembic upgrade head` уже описан.

- [ ] **Step 5: Прогнать проверочный гейт целиком**

Run: `cd apps/api && pytest -v`
Expected: PASS

Run: `cd apps/web && npm run lint && npm run test:e2e`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add apps/web/app/\(dashboard\)/jobs/runs apps/web/tests/jobs.spec.ts CLAUDE.md
git commit -m "feat(web): job run detail page, e2e coverage and docs"
```

---

## Self-Review

**Покрытие спеки:**

| Требование спеки | Задача |
|---|---|
| Таблицы `jobs`/`job_runs`/`job_run_items` + миграция + сиды 4 задач | 1 |
| `MetricsService` вынесен из CLI | 2 |
| `JobService`: правка задач, создание запусков, листинги, retention 20 дней | 3 |
| Guard повторного запуска через блокировку строки | 3 (сервис), 6 (409 в API) |
| `JobRunner` — метрики, агрегация статусов, последовательность с задержкой | 4 |
| `JobRunner` — отзывы, сравнение счётчиков, `scrape_run_id` в логе | 5 |
| API `GET/PATCH /api/jobs`, `POST .../run`, `GET /api/job-runs[/{id}]`, admin-гейт | 6 |
| APScheduler в lifespan, флаг, ночная очистка | 7 |
| Веб-типы и клиент | 8 |
| Страница `/jobs`: карточки, расписание, таблица, фильтры, polling 5s | 9 |
| Деталь запуска, E2E, документация | 10 |

**Вне рамок (подтверждено):** Celery/очереди, параллелизм, расписание на организацию, Google, обход капчи, правка `scrape_runs`, уведомления.
