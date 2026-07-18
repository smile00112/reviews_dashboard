# Attention Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operator-managed rules (type, thresholds, scope, severity) replace the five hardcoded attention-feed triggers on `/overview`.

**Architecture:** New `attention_rules` table (migration 0015, seeded with 5 global rules matching current hardcoded behavior) + `AttentionRuleService` CRUD + `/api/attention-rules` router (mutations admin-only). `DashboardService._attention` becomes rule-driven: loads enabled rules, resolves each rule's scope to an org set, intersects with page filters, evaluates the existing per-type logic with the rule's params. No persisted events — evaluation stays on-the-fly. Web: new `/attention-rules` page (list + form), gear link in the overview attention panel.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Pydantic v2 (apps/api), Next.js App Router + Tailwind (apps/web), pytest (SQLite in tests), Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-07-18-attention-rules-design.md`

## Global Constraints

- Constitution: read-only product; no Celery/queues; no LLM; mutations `require_admin`, reads under session (`get_current_user`) — the overview endpoint already requires a session.
- JSONB columns must use `JSON().with_variant(JSONB, "postgresql")` — tests run on SQLite.
- Enum columns: `Enum(PyEnum, name="..._enum", values_callable=lambda x: [e.value for e in x])` (project pattern, see `models/job.py`).
- Migration `0015_attention_rules` branches from head `0014_background_jobs`; Postgres enum types created/dropped explicitly with `create_type=False` on column defs (pattern from `0014_background_jobs.py`).
- Seeds: 5 global enabled rules with current hardcoded defaults; dashboard behavior must not change after deploy (existing dashboard tests keep passing once they seed the same defaults).
- Backend run dir: `apps/api`. Web run dir: `apps/web`. Verification gate: `pytest -v` (api), `npm run lint` (web).
- All UI copy in Russian (project convention).
- Python: `from __future__ import annotations` not required in new files unless needed; match neighboring file style.

---

### Task 1: Enums, model, migration 0015

**Files:**
- Modify: `apps/api/app/models/enums.py`
- Create: `apps/api/app/models/attention_rule.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/alembic/versions/0015_attention_rules.py`
- Test: `apps/api/tests/test_attention_rules_api.py` (model roundtrip test only in this task)

**Interfaces:**
- Produces: enums `AttentionRuleType` (`unanswered_overdue|fresh_negative|escalated|rating_drop|aspect_spike`), `AttentionSeverity` (`urgent|warn|info`), `AttentionScope` (member `global_` with value `"global"`, `company`, `organizations`) in `app.models.enums`; ORM model `AttentionRule` (table `attention_rules`) with columns `id, rule_type, name, is_enabled, severity, params (dict), scope_type, company_id, organization_ids (list), created_at, updated_at`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_attention_rules_api.py`:

```python
"""CRUD contract + validation for /api/attention-rules (attention rules feature)."""

import uuid

from app.models.attention_rule import AttentionRule
from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity


def test_model_roundtrip_defaults(db_session):
    rule = AttentionRule(
        rule_type=AttentionRuleType.unanswered_overdue,
        severity=AttentionSeverity.urgent,
        params={"hours": 24},
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    assert isinstance(rule.id, uuid.UUID)
    assert rule.is_enabled is True
    assert rule.name is None
    assert rule.scope_type == AttentionScope.global_
    assert rule.company_id is None
    assert rule.organization_ids == []
    assert rule.params == {"hours": 24}
    assert rule.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.attention_rule'` (or ImportError on the enums).

- [ ] **Step 3: Add enums**

Append to `apps/api/app/models/enums.py`:

```python
class AttentionRuleType(str, enum.Enum):
    unanswered_overdue = "unanswered_overdue"
    fresh_negative = "fresh_negative"
    escalated = "escalated"
    rating_drop = "rating_drop"
    aspect_spike = "aspect_spike"


class AttentionSeverity(str, enum.Enum):
    urgent = "urgent"
    warn = "warn"
    info = "info"


class AttentionScope(str, enum.Enum):
    # "global" is a Python keyword, so the member is global_; the DB/API value
    # stays "global" (values_callable pattern on the columns).
    global_ = "global"
    company = "company"
    organizations = "organizations"
```

- [ ] **Step 4: Add the model**

Create `apps/api/app/models/attention_rule.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity


class AttentionRule(Base):
    """Настраиваемое правило блока «Требуют внимания» на /overview."""

    __tablename__ = "attention_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_type: Mapped[AttentionRuleType] = mapped_column(
        Enum(AttentionRuleType, name="attention_rule_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[AttentionSeverity] = mapped_column(
        Enum(AttentionSeverity, name="attention_severity_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    params: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    scope_type: Mapped[AttentionScope] = mapped_column(
        Enum(AttentionScope, name="attention_scope_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AttentionScope.global_,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    # JSONB-список строковых UUID, не M2M: организаций десятки, удаляются редко;
    # несуществующие id при оценке молча игнорируются.
    organization_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

Register in `apps/api/app/models/__init__.py` (keep alphabetical):

```python
from app.models.attention_rule import AttentionRule
```
and add `"AttentionRule",` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: PASS.

- [ ] **Step 6: Write migration**

Create `apps/api/alembic/versions/0015_attention_rules.py`:

```python
"""attention rules: configurable triggers for the overview attention feed

Revision ID: 0015_attention_rules
Revises: 0014_background_jobs
Create Date: 2026-07-18

Additive. Seeds 5 global enabled rules replicating the previously hardcoded
thresholds in DashboardService._attention, so dashboard behavior does not
change on deploy.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_attention_rules"
down_revision: Union[str, None] = "0014_background_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: types are created/dropped explicitly below (см. 0014).
rule_type_enum = postgresql.ENUM(
    "unanswered_overdue", "fresh_negative", "escalated", "rating_drop", "aspect_spike",
    name="attention_rule_type_enum", create_type=False,
)
severity_enum = postgresql.ENUM("urgent", "warn", "info", name="attention_severity_enum", create_type=False)
scope_enum = postgresql.ENUM("global", "company", "organizations", name="attention_scope_enum", create_type=False)

# Сиды = текущие захардкоженные пороги DashboardService._attention.
SEED_RULES = [
    ("unanswered_overdue", "urgent", {"hours": 24}),
    ("fresh_negative", "urgent", {"window_hours": 2, "max_rating": 2}),
    ("escalated", "warn", {}),
    ("rating_drop", "warn", {"threshold": -0.2, "top": 3}),
    ("aspect_spike", "warn", {"min_recent": 3, "top": 3}),
]


def upgrade() -> None:
    bind = op.get_bind()
    rule_type_enum.create(bind, checkfirst=True)
    severity_enum.create(bind, checkfirst=True)
    scope_enum.create(bind, checkfirst=True)

    table = op.create_table(
        "attention_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_type", rule_type_enum, nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("scope_type", scope_enum, nullable=False, server_default="global"),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("organization_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(), "rule_type": rule_type, "name": None,
                "is_enabled": True, "severity": severity, "params": params,
                "scope_type": "global", "company_id": None, "organization_ids": [],
            }
            for rule_type, severity, params in SEED_RULES
        ],
    )


def downgrade() -> None:
    op.drop_table("attention_rules")
    bind = op.get_bind()
    scope_enum.drop(bind, checkfirst=True)
    severity_enum.drop(bind, checkfirst=True)
    rule_type_enum.drop(bind, checkfirst=True)
```

- [ ] **Step 7: Verify migration syntax and full suite**

From `apps/api`:
- `python -c "import importlib.util; spec = importlib.util.spec_from_file_location('m', 'alembic/versions/0015_attention_rules.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.revision, m.down_revision)"`
  Expected: `0015_attention_rules 0014_background_jobs`
- `pytest -v` — Expected: all pass (migration itself is not executed by SQLite tests; `Base.metadata.create_all` builds the table from the model).

If a live Postgres is available (docker compose up), also run `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` to confirm clean up/down. Not a blocker for commit if no DB is running.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models/enums.py apps/api/app/models/attention_rule.py apps/api/app/models/__init__.py apps/api/alembic/versions/0015_attention_rules.py apps/api/tests/test_attention_rules_api.py
git commit -m "feat(api): attention_rules model + migration 0015 with seeded defaults"
```

---

### Task 2: Pydantic schemas with per-type params validation

**Files:**
- Create: `apps/api/app/schemas/attention_rule.py`
- Test: `apps/api/tests/test_attention_rules_api.py` (append)

**Interfaces:**
- Consumes: enums from Task 1.
- Produces: `PARAM_MODELS: dict[AttentionRuleType, type[BaseModel]]`; `AttentionRuleCreate` (fields: `rule_type, name, is_enabled, severity, params, scope_type, company_id, organization_ids`), `AttentionRuleUpdate` (all optional, no `rule_type`), `AttentionRuleResponse` (`from_attributes`), `AttentionRuleListResponse(items=...)`. Param models: `UnansweredOverdueParams(hours=24, ge=1)`, `FreshNegativeParams(window_hours=2 ge=1, max_rating=2 1..4)`, `EscalatedParams` (empty), `RatingDropParams(threshold=-0.2 lt=0, top=3 1..10)`, `AspectSpikeParams(min_recent=3 ge=1, top=3 1..10)`. All param models `extra="forbid"`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_attention_rules_api.py`:

```python
import pytest
from pydantic import ValidationError


def test_param_models_defaults_and_forbid_extra():
    from app.schemas.attention_rule import (
        PARAM_MODELS,
        FreshNegativeParams,
        RatingDropParams,
        UnansweredOverdueParams,
    )

    assert UnansweredOverdueParams().hours == 24
    assert FreshNegativeParams().model_dump() == {"window_hours": 2, "max_rating": 2}
    assert RatingDropParams().model_dump() == {"threshold": -0.2, "top": 3}
    assert set(PARAM_MODELS) == set(AttentionRuleType)

    with pytest.raises(ValidationError):
        UnansweredOverdueParams(hours=0)          # ge=1
    with pytest.raises(ValidationError):
        FreshNegativeParams(max_rating=5)          # le=4
    with pytest.raises(ValidationError):
        RatingDropParams(threshold=0.1)            # lt=0
    with pytest.raises(ValidationError):
        UnansweredOverdueParams(hours=24, bogus=1)  # extra="forbid"
```

- [ ] **Step 2: Run tests to verify they fail**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: new test FAILS with `ModuleNotFoundError: No module named 'app.schemas.attention_rule'`.

- [ ] **Step 3: Write the schemas**

Create `apps/api/app/schemas/attention_rule.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity


# --- Параметры по типам правила (extra="forbid": лишний ключ = 422) ----------

class UnansweredOverdueParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: int = Field(default=24, ge=1)


class FreshNegativeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_hours: int = Field(default=2, ge=1)
    max_rating: int = Field(default=2, ge=1, le=4)


class EscalatedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RatingDropParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = Field(default=-0.2, lt=0)
    top: int = Field(default=3, ge=1, le=10)


class AspectSpikeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_recent: int = Field(default=3, ge=1)
    top: int = Field(default=3, ge=1, le=10)


PARAM_MODELS: dict[AttentionRuleType, type[BaseModel]] = {
    AttentionRuleType.unanswered_overdue: UnansweredOverdueParams,
    AttentionRuleType.fresh_negative: FreshNegativeParams,
    AttentionRuleType.escalated: EscalatedParams,
    AttentionRuleType.rating_drop: RatingDropParams,
    AttentionRuleType.aspect_spike: AspectSpikeParams,
}


# --- CRUD-схемы ---------------------------------------------------------------

class AttentionRuleCreate(BaseModel):
    rule_type: AttentionRuleType
    name: str | None = Field(default=None, max_length=200)
    is_enabled: bool = True
    severity: AttentionSeverity
    params: dict = Field(default_factory=dict)
    scope_type: AttentionScope = AttentionScope.global_
    company_id: UUID | None = None
    organization_ids: list[UUID] = Field(default_factory=list)


class AttentionRuleUpdate(BaseModel):
    # rule_type менять нельзя — поля нет; params валидируются по типу правила в сервисе.
    name: str | None = Field(default=None, max_length=200)
    is_enabled: bool | None = None
    severity: AttentionSeverity | None = None
    params: dict | None = None
    scope_type: AttentionScope | None = None
    company_id: UUID | None = None
    organization_ids: list[UUID] | None = None


class AttentionRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_type: AttentionRuleType
    name: str | None
    is_enabled: bool
    severity: AttentionSeverity
    params: dict
    scope_type: AttentionScope
    company_id: UUID | None
    organization_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class AttentionRuleListResponse(BaseModel):
    items: list[AttentionRuleResponse]
```

- [ ] **Step 4: Run tests to verify they pass**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas/attention_rule.py apps/api/tests/test_attention_rules_api.py
git commit -m "feat(api): attention rule schemas with per-type params validation"
```

---

### Task 3: AttentionRuleService (CRUD + scope validation + seed_defaults)

**Files:**
- Create: `apps/api/app/services/attention_rule_service.py`
- Test: `apps/api/tests/test_attention_rules_api.py` (append)

**Interfaces:**
- Consumes: `AttentionRule` model, `PARAM_MODELS`, `AttentionRuleCreate/Update` schemas.
- Produces: `AttentionRuleValidationError(ValueError)`; `AttentionRuleService(db)` with methods `list_rules() -> list[AttentionRule]`, `get(rule_id) -> AttentionRule | None`, `create(payload: AttentionRuleCreate) -> AttentionRule`, `update(rule_id, payload: AttentionRuleUpdate) -> AttentionRule | None` (None = not found), `delete(rule_id) -> bool`, `seed_defaults() -> list[AttentionRule]`; module constant `DEFAULT_RULES`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_attention_rules_api.py`:

```python
from app.models.company import Company
from app.models.organization import Organization
from app.schemas.attention_rule import AttentionRuleCreate, AttentionRuleUpdate


def _make_service(db):
    from app.services.attention_rule_service import AttentionRuleService
    return AttentionRuleService(db)


def _make_org(db, name="Org"):
    org = Organization(name=name, rating=4.5, review_count=10)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_service_create_normalizes_params_with_defaults(db_session):
    svc = _make_service(db_session)
    rule = svc.create(AttentionRuleCreate(
        rule_type=AttentionRuleType.fresh_negative,
        severity=AttentionSeverity.urgent,
        params={"window_hours": 6},
    ))
    # max_rating дозаполнен дефолтом
    assert rule.params == {"window_hours": 6, "max_rating": 2}
    assert rule.scope_type == AttentionScope.global_


def test_service_create_rejects_bad_params(db_session):
    from app.services.attention_rule_service import AttentionRuleValidationError
    svc = _make_service(db_session)
    with pytest.raises(AttentionRuleValidationError):
        svc.create(AttentionRuleCreate(
            rule_type=AttentionRuleType.unanswered_overdue,
            severity=AttentionSeverity.urgent,
            params={"hours": 24, "bogus": 1},
        ))


def test_service_scope_company_requires_existing_company(db_session):
    from app.services.attention_rule_service import AttentionRuleValidationError
    svc = _make_service(db_session)
    with pytest.raises(AttentionRuleValidationError):
        svc.create(AttentionRuleCreate(
            rule_type=AttentionRuleType.escalated,
            severity=AttentionSeverity.warn,
            scope_type=AttentionScope.company,
        ))  # company_id отсутствует
    with pytest.raises(AttentionRuleValidationError):
        svc.create(AttentionRuleCreate(
            rule_type=AttentionRuleType.escalated,
            severity=AttentionSeverity.warn,
            scope_type=AttentionScope.company,
            company_id=uuid.uuid4(),
        ))  # company не существует

    company = Company(name="Сеть")
    db_session.add(company)
    db_session.commit()
    rule = svc.create(AttentionRuleCreate(
        rule_type=AttentionRuleType.escalated,
        severity=AttentionSeverity.warn,
        scope_type=AttentionScope.company,
        company_id=company.id,
        organization_ids=[uuid.uuid4()],  # должен быть очищен
    ))
    assert rule.company_id == company.id
    assert rule.organization_ids == []


def test_service_scope_organizations_validates_ids(db_session):
    from app.services.attention_rule_service import AttentionRuleValidationError
    svc = _make_service(db_session)
    with pytest.raises(AttentionRuleValidationError):
        svc.create(AttentionRuleCreate(
            rule_type=AttentionRuleType.escalated,
            severity=AttentionSeverity.warn,
            scope_type=AttentionScope.organizations,
            organization_ids=[],
        ))  # пустой список
    with pytest.raises(AttentionRuleValidationError):
        svc.create(AttentionRuleCreate(
            rule_type=AttentionRuleType.escalated,
            severity=AttentionSeverity.warn,
            scope_type=AttentionScope.organizations,
            organization_ids=[uuid.uuid4()],
        ))  # id не существует

    org = _make_org(db_session)
    rule = svc.create(AttentionRuleCreate(
        rule_type=AttentionRuleType.escalated,
        severity=AttentionSeverity.warn,
        scope_type=AttentionScope.organizations,
        organization_ids=[org.id],
    ))
    assert rule.organization_ids == [str(org.id)]
    assert rule.company_id is None


def test_service_update_revalidates_params_and_scope(db_session):
    from app.services.attention_rule_service import AttentionRuleValidationError
    svc = _make_service(db_session)
    rule = svc.create(AttentionRuleCreate(
        rule_type=AttentionRuleType.unanswered_overdue,
        severity=AttentionSeverity.urgent,
    ))
    updated = svc.update(rule.id, AttentionRuleUpdate(params={"hours": 48}, is_enabled=False))
    assert updated.params == {"hours": 48}
    assert updated.is_enabled is False

    with pytest.raises(AttentionRuleValidationError):
        svc.update(rule.id, AttentionRuleUpdate(params={"window_hours": 1}))  # чужой ключ для типа

    assert svc.update(uuid.uuid4(), AttentionRuleUpdate(is_enabled=True)) is None


def test_service_delete(db_session):
    svc = _make_service(db_session)
    rule = svc.create(AttentionRuleCreate(
        rule_type=AttentionRuleType.escalated, severity=AttentionSeverity.warn,
    ))
    assert svc.delete(rule.id) is True
    assert svc.delete(rule.id) is False
    assert svc.list_rules() == []


def test_seed_defaults_creates_five_rules_once(db_session):
    svc = _make_service(db_session)
    created = svc.seed_defaults()
    assert len(created) == 5
    assert {r.rule_type for r in created} == set(AttentionRuleType)
    assert all(r.is_enabled and r.scope_type == AttentionScope.global_ for r in created)
    # Повторный вызов — no-op.
    assert svc.seed_defaults() == []
    assert len(svc.list_rules()) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: new tests FAIL with `ModuleNotFoundError: No module named 'app.services.attention_rule_service'`.

- [ ] **Step 3: Write the service**

Create `apps/api/app/services/attention_rule_service.py`:

```python
"""CRUD + валидация настраиваемых правил блока «Требуют внимания».

Оценка правил живёт в DashboardService._attention; здесь только управление
строками attention_rules. Мутации дергаются из admin-only роутера.
"""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.attention_rule import AttentionRule
from app.models.company import Company
from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity
from app.models.organization import Organization
from app.schemas.attention_rule import PARAM_MODELS, AttentionRuleCreate, AttentionRuleUpdate

# Дефолты = сиды миграции 0015 (продублированы: миграции заморожены и не
# импортируют app-код). Используются тестами и seed_defaults().
DEFAULT_RULES: list[dict] = [
    {"rule_type": AttentionRuleType.unanswered_overdue, "severity": AttentionSeverity.urgent,
     "params": {"hours": 24}},
    {"rule_type": AttentionRuleType.fresh_negative, "severity": AttentionSeverity.urgent,
     "params": {"window_hours": 2, "max_rating": 2}},
    {"rule_type": AttentionRuleType.escalated, "severity": AttentionSeverity.warn, "params": {}},
    {"rule_type": AttentionRuleType.rating_drop, "severity": AttentionSeverity.warn,
     "params": {"threshold": -0.2, "top": 3}},
    {"rule_type": AttentionRuleType.aspect_spike, "severity": AttentionSeverity.warn,
     "params": {"min_recent": 3, "top": 3}},
]


class AttentionRuleValidationError(ValueError):
    """Невалидные params или scope; роутер отдаёт 422 с этим текстом."""


class AttentionRuleService:
    def __init__(self, db: Session):
        self.db = db

    # --- чтение ---------------------------------------------------------- #
    def list_rules(self) -> list[AttentionRule]:
        return self.db.query(AttentionRule).order_by(AttentionRule.created_at).all()

    def get(self, rule_id: UUID) -> AttentionRule | None:
        return self.db.get(AttentionRule, rule_id)

    # --- валидация ------------------------------------------------------- #
    def _normalize_params(self, rule_type: AttentionRuleType, params: dict) -> dict:
        model = PARAM_MODELS[rule_type]
        try:
            return model(**(params or {})).model_dump()
        except ValidationError as exc:
            raise AttentionRuleValidationError(f"Некорректные параметры правила: {exc}") from exc

    def _validated_scope(
        self,
        scope_type: AttentionScope,
        company_id: UUID | None,
        organization_ids: list[UUID] | None,
    ) -> tuple[UUID | None, list[str]]:
        """Возвращает (company_id, organization_ids-as-str) после проверки скоупа."""
        if scope_type == AttentionScope.company:
            if company_id is None:
                raise AttentionRuleValidationError("scope=company требует company_id")
            if self.db.get(Company, company_id) is None:
                raise AttentionRuleValidationError("Компания не найдена")
            return company_id, []
        if scope_type == AttentionScope.organizations:
            ids = list(dict.fromkeys(organization_ids or []))  # dedup, порядок сохранён
            if not ids:
                raise AttentionRuleValidationError("scope=organizations требует непустой organization_ids")
            found = {
                row[0]
                for row in self.db.query(Organization.id).filter(Organization.id.in_(ids)).all()
            }
            missing = [str(i) for i in ids if i not in found]
            if missing:
                raise AttentionRuleValidationError(f"Организации не найдены: {', '.join(missing)}")
            return None, [str(i) for i in ids]
        return None, []  # global: скоуп-поля обнуляются

    # --- мутации ---------------------------------------------------------- #
    def create(self, payload: AttentionRuleCreate) -> AttentionRule:
        params = self._normalize_params(payload.rule_type, payload.params)
        company_id, org_ids = self._validated_scope(
            payload.scope_type, payload.company_id, payload.organization_ids
        )
        rule = AttentionRule(
            rule_type=payload.rule_type,
            name=payload.name,
            is_enabled=payload.is_enabled,
            severity=payload.severity,
            params=params,
            scope_type=payload.scope_type,
            company_id=company_id,
            organization_ids=org_ids,
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update(self, rule_id: UUID, payload: AttentionRuleUpdate) -> AttentionRule | None:
        rule = self.get(rule_id)
        if rule is None:
            return None
        data = payload.model_dump(exclude_unset=True)

        if "params" in data and data["params"] is not None:
            rule.params = self._normalize_params(rule.rule_type, data["params"])
        if "name" in data:
            rule.name = data["name"]
        if data.get("is_enabled") is not None:
            rule.is_enabled = data["is_enabled"]
        if data.get("severity") is not None:
            rule.severity = data["severity"]

        # Скоуп ревалидируется целиком, если тронуто любое из трёх полей.
        if any(k in data for k in ("scope_type", "company_id", "organization_ids")):
            scope_type = data.get("scope_type") or rule.scope_type
            company_id = data["company_id"] if "company_id" in data else rule.company_id
            raw_org_ids = (
                data["organization_ids"] if "organization_ids" in data
                else [UUID(str(i)) for i in (rule.organization_ids or [])]
            )
            rule.company_id, rule.organization_ids = self._validated_scope(
                scope_type, company_id, raw_org_ids
            )
            rule.scope_type = scope_type

        self.db.commit()
        self.db.refresh(rule)
        return rule

    def delete(self, rule_id: UUID) -> bool:
        rule = self.get(rule_id)
        if rule is None:
            return False
        self.db.delete(rule)
        self.db.commit()
        return True

    # --- сиды для тестов/бутстрапа ---------------------------------------- #
    def seed_defaults(self) -> list[AttentionRule]:
        """Создаёт 5 глобальных правил-дефолтов, если таблица пуста (no-op иначе)."""
        if self.db.query(AttentionRule.id).first() is not None:
            return []
        created = [AttentionRule(**spec) for spec in DEFAULT_RULES]
        self.db.add_all(created)
        self.db.commit()
        return created
```

- [ ] **Step 4: Run tests to verify they pass**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/attention_rule_service.py apps/api/tests/test_attention_rules_api.py
git commit -m "feat(api): AttentionRuleService with scope/params validation and seed_defaults"
```

---

### Task 4: Router /api/attention-rules + auth gates

**Files:**
- Create: `apps/api/app/api/attention_rules.py`
- Modify: `apps/api/app/main.py` (register router)
- Test: `apps/api/tests/test_attention_rules_api.py` (append)

**Interfaces:**
- Consumes: `AttentionRuleService`, schemas from Task 2, deps `get_current_user`/`require_admin` from `app.api.deps`.
- Produces: `GET /api/attention-rules` → `AttentionRuleListResponse` (session); `POST` → 201 `AttentionRuleResponse` (admin); `PATCH /{rule_id}` → `AttentionRuleResponse` (admin, 404 if missing); `DELETE /{rule_id}` → 204 (admin, 404 if missing); validation errors → 422 with the service message.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_attention_rules_api.py`:

```python
# --- HTTP contract ------------------------------------------------------------

def _payload(**over):
    base = {
        "rule_type": "unanswered_overdue",
        "severity": "urgent",
        "params": {"hours": 12},
    }
    base.update(over)
    return base


def test_list_requires_session(client):
    assert client.get("/api/attention-rules").status_code == 401


def test_mutations_require_admin(client, operator_client):
    # 401 без сессии
    assert client.post("/api/attention-rules", json=_payload()).status_code == 401
    # 403 под review_operator
    assert operator_client.post("/api/attention-rules", json=_payload()).status_code == 403
    fake_id = str(uuid.uuid4())
    assert operator_client.patch(f"/api/attention-rules/{fake_id}", json={"is_enabled": False}).status_code == 403
    assert operator_client.delete(f"/api/attention-rules/{fake_id}").status_code == 403


def test_crud_flow(admin_client):
    created = admin_client.post("/api/attention-rules", json=_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["rule_type"] == "unanswered_overdue"
    assert body["params"] == {"hours": 12}
    assert body["scope_type"] == "global"
    rule_id = body["id"]

    listed = admin_client.get("/api/attention-rules").json()["items"]
    assert [r["id"] for r in listed] == [rule_id]

    patched = admin_client.patch(
        f"/api/attention-rules/{rule_id}", json={"is_enabled": False, "name": "Ночной SLA"}
    )
    assert patched.status_code == 200
    assert patched.json()["is_enabled"] is False
    assert patched.json()["name"] == "Ночной SLA"

    assert admin_client.delete(f"/api/attention-rules/{rule_id}").status_code == 204
    assert admin_client.get("/api/attention-rules").json()["items"] == []


def test_create_invalid_params_422(admin_client):
    resp = admin_client.post("/api/attention-rules", json=_payload(params={"hours": 12, "bogus": 1}))
    assert resp.status_code == 422


def test_create_invalid_scope_422(admin_client):
    resp = admin_client.post(
        "/api/attention-rules",
        json=_payload(scope_type="organizations", organization_ids=[str(uuid.uuid4())]),
    )
    assert resp.status_code == 422
    assert "не найдены" in resp.json()["detail"]


def test_patch_and_delete_missing_404(admin_client):
    fake_id = str(uuid.uuid4())
    assert admin_client.patch(f"/api/attention-rules/{fake_id}", json={"is_enabled": True}).status_code == 404
    assert admin_client.delete(f"/api/attention-rules/{fake_id}").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: new tests FAIL with 404 (route not registered).

- [ ] **Step 3: Write the router and register it**

Create `apps/api/app/api/attention_rules.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.schemas.attention_rule import (
    AttentionRuleCreate,
    AttentionRuleListResponse,
    AttentionRuleResponse,
    AttentionRuleUpdate,
)
from app.services.attention_rule_service import AttentionRuleService, AttentionRuleValidationError

router = APIRouter(prefix="/api/attention-rules", tags=["attention-rules"])


@router.get("", response_model=AttentionRuleListResponse)
def list_rules(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> AttentionRuleListResponse:
    items = [AttentionRuleResponse.model_validate(r) for r in AttentionRuleService(db).list_rules()]
    return AttentionRuleListResponse(items=items)


@router.post("", response_model=AttentionRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: AttentionRuleCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> AttentionRuleResponse:
    try:
        return AttentionRuleResponse.model_validate(AttentionRuleService(db).create(payload))
    except AttentionRuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{rule_id}", response_model=AttentionRuleResponse)
def update_rule(
    rule_id: UUID,
    payload: AttentionRuleUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> AttentionRuleResponse:
    try:
        rule = AttentionRuleService(db).update(rule_id, payload)
    except AttentionRuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    return AttentionRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> None:
    if not AttentionRuleService(db).delete(rule_id):
        raise HTTPException(status_code=404, detail="Правило не найдено")
```

In `apps/api/app/main.py`: add `attention_rules` to the existing `from app.api import ...` import and register after the dashboard router:

```python
app.include_router(attention_rules.router)
```

- [ ] **Step 4: Run tests to verify they pass**

From `apps/api`: `pytest tests/test_attention_rules_api.py -v`
Expected: PASS. Then `pytest -v` — full suite green.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/attention_rules.py apps/api/app/main.py apps/api/tests/test_attention_rules_api.py
git commit -m "feat(api): /api/attention-rules CRUD router, mutations admin-only"
```

---

### Task 5: Rule-driven DashboardService._attention

**Files:**
- Modify: `apps/api/app/services/dashboard_service.py` (replace `_attention`, `_aspect_spikes`, `_rating_drops`; add helpers)
- Modify: `apps/api/app/schemas/dashboard.py` (extend `AttentionItem`)
- Modify: `apps/api/tests/test_dashboard_overview.py` (seed rules in attention tests)
- Test: Create `apps/api/tests/test_dashboard_attention_rules.py`

**Interfaces:**
- Consumes: `AttentionRule`, `AttentionScope`, `AttentionRuleType` enums; `AttentionRuleService.seed_defaults` (tests only).
- Produces: `_attention(orgs, all_reviews, platform, snaps, now)` keeps its signature but reads enabled rules from `self.db`. Each item dict gains `rule_id` (UUID) and `rule_name` (str|None). `AttentionItem` schema gains `rule_id: UUID | None = None`, `rule_name: str | None = None`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_dashboard_attention_rules.py`:

```python
"""Rule-driven attention feed: scoping, thresholds, enable/disable (attention rules feature)."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.company import Company
from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity, ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.schemas.attention_rule import AttentionRuleCreate
from app.services.attention_rule_service import AttentionRuleService

NOW = datetime.now(timezone.utc)


def _org(db, name="Org", company_id=None):
    org = Organization(name=name, rating=4.5, review_count=10, company_id=company_id)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, rating=4, first_seen, hash_):
    r = Review(
        organization_id=org.id, source="yandex_maps", scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex, rating=rating, review_text="text",
        content_hash=hash_, first_seen_at=first_seen, last_seen_at=first_seen,
    )
    db.add(r)
    db.commit()
    return r


def _rule(db, **over):
    payload = {
        "rule_type": AttentionRuleType.unanswered_overdue,
        "severity": AttentionSeverity.urgent,
        "params": {},
    }
    payload.update(over)
    return AttentionRuleService(db).create(AttentionRuleCreate(**payload))


def _attention(admin_client, query=""):
    return admin_client.get(f"/api/dashboard/overview?period=30d{query}").json()["attention"]


def test_no_rules_empty_feed(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    assert _attention(admin_client) == []


def test_seeded_defaults_match_previous_behavior(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")     # overdue
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(hours=1), hash_="h2")  # fresh negative
    AttentionRuleService(db_session).seed_defaults()

    items = _attention(admin_client)
    types = {i["type"] for i in items}
    assert "unanswered_overdue" in types
    assert "fresh_negative" in types
    for item in items:
        assert item["rule_id"] is not None
        assert item["rule_name"] is None


def test_disabled_rule_produces_nothing(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    _rule(db_session, params={"hours": 24}, is_enabled=False)
    assert _attention(admin_client) == []


def test_custom_threshold_changes_result(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=10), hash_="h1")  # 10h unanswered

    strict = _rule(db_session, params={"hours": 1}, name="Строгий SLA")
    items = _attention(admin_client)
    assert len(items) == 1
    assert items[0]["title"].endswith("> 1ч")
    assert items[0]["rule_name"] == "Строгий SLA"
    assert items[0]["subtitle"].startswith("Строгий SLA · ")

    AttentionRuleService(db_session).delete(strict.id)
    _rule(db_session, params={"hours": 48})
    assert _attention(admin_client) == []  # 10h < 48h


def test_company_scope_counts_only_company_orgs(admin_client, db_session):
    company = Company(name="Сеть")
    db_session.add(company)
    db_session.commit()
    inside = _org(db_session, name="In", company_id=company.id)
    outside = _org(db_session, name="Out")
    _review(db_session, inside, first_seen=NOW - timedelta(hours=48), hash_="in1")
    _review(db_session, outside, first_seen=NOW - timedelta(hours=48), hash_="out1")

    _rule(db_session, params={"hours": 24}, scope_type=AttentionScope.company, company_id=company.id)
    items = _attention(admin_client)
    assert len(items) == 1
    assert items[0]["value"] == 1  # только inside


def test_org_scope_and_stale_org_id_ignored(admin_client, db_session):
    target = _org(db_session, name="Target")
    other = _org(db_session, name="Other")
    _review(db_session, target, first_seen=NOW - timedelta(hours=48), hash_="t1")
    _review(db_session, other, first_seen=NOW - timedelta(hours=48), hash_="o1")

    rule = _rule(db_session, params={"hours": 24},
                 scope_type=AttentionScope.organizations, organization_ids=[target.id])
    # Появившийся мусорный id (после удаления организации) игнорируется молча.
    db_rule = AttentionRuleService(db_session).get(rule.id)
    db_rule.organization_ids = [str(target.id), str(uuid.uuid4())]
    db_session.commit()

    items = _attention(admin_client)
    assert len(items) == 1
    assert items[0]["value"] == 1  # только target


def test_two_rules_same_type_two_items(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    _rule(db_session, params={"hours": 24}, name="Сутки")
    _rule(db_session, params={"hours": 12}, name="Полсуток")

    items = _attention(admin_client)
    assert len(items) == 2
    assert {i["rule_name"] for i in items} == {"Сутки", "Полсуток"}


def test_rule_scope_intersects_page_filter(admin_client, db_session):
    company = Company(name="Сеть")
    db_session.add(company)
    db_session.commit()
    inside = _org(db_session, name="In", company_id=company.id)
    _review(db_session, inside, first_seen=NOW - timedelta(hours=48), hash_="in1")

    _rule(db_session, params={"hours": 24}, scope_type=AttentionScope.company, company_id=company.id)
    # Фильтр страницы по другой (пустой) выборке организаций — пересечение пусто.
    other = _org(db_session, name="Other")
    items = _attention(admin_client, query=f"&org_ids={other.id}")
    assert items == []
```

- [ ] **Step 2: Run tests to verify they fail**

From `apps/api`: `pytest tests/test_dashboard_attention_rules.py -v`
Expected: FAIL — `test_no_rules_empty_feed` and others fail because `_attention` still hardcodes rules (feed non-empty without any rules; no `rule_id` key).

- [ ] **Step 3: Extend AttentionItem schema**

In `apps/api/app/schemas/dashboard.py` (add `from uuid import UUID` to imports if absent):

```python
class AttentionItem(BaseModel):
    type: str
    title: str
    subtitle: str
    value: float
    severity: str
    link: str
    rule_id: UUID | None = None
    rule_name: str | None = None
```

- [ ] **Step 4: Rewrite the attention section in DashboardService**

In `apps/api/app/services/dashboard_service.py`:

Add imports:

```python
from app.models.attention_rule import AttentionRule
from app.models.enums import AttentionRuleType, AttentionScope
```
(merge with the existing `from app.models.enums import ReviewPlatform, ReviewStatus` line).

Replace the whole attention block (`_SEVERITY_ORDER`, `_attention`, `_aspect_spikes`, `_rating_drops` — currently `dashboard_service.py:413-522`) with:

```python
    # ------------------------------------------------------------------ #
    # Attention feed — управляется правилами attention_rules              #
    # ------------------------------------------------------------------ #
    _SEVERITY_ORDER = {"urgent": 0, "warn": 1, "info": 2}

    def _attention(self, orgs, all_reviews, platform, snaps, now) -> list[dict]:
        rules = (
            self.db.query(AttentionRule)
            .filter(AttentionRule.is_enabled.is_(True))
            .order_by(AttentionRule.created_at)
            .all()
        )
        items: list[dict] = []
        for rule in rules:
            scope_ids = self._rule_scope_ids(rule, orgs)
            if not scope_ids:
                continue  # скоуп не пересекается с фильтрами страницы
            rule_orgs = [o for o in orgs if o.id in scope_ids]
            rule_reviews = [r for r in all_reviews if r.organization_id in scope_ids]
            items.extend(self._evaluate_rule(rule, rule_orgs, rule_reviews, platform, snaps, now))
        items.sort(key=lambda i: (self._SEVERITY_ORDER.get(i["severity"], 9), -i["value"]))
        return items

    @staticmethod
    def _rule_scope_ids(rule: AttentionRule, orgs) -> set[UUID]:
        selected = {o.id for o in orgs}
        if rule.scope_type == AttentionScope.company:
            return {o.id for o in orgs if o.company_id == rule.company_id}
        if rule.scope_type == AttentionScope.organizations:
            wanted: set[UUID] = set()
            for raw in rule.organization_ids or []:
                try:
                    wanted.add(UUID(str(raw)))
                except ValueError:
                    continue  # мусорный id (организация удалена) — игнорируем
            return selected & wanted
        return selected

    def _evaluate_rule(self, rule, rule_orgs, rule_reviews, platform, snaps, now) -> list[dict]:
        params = rule.params or {}
        if rule.rule_type == AttentionRuleType.unanswered_overdue:
            found = self._eval_unanswered(rule_reviews, now, hours=int(params.get("hours", 24)))
        elif rule.rule_type == AttentionRuleType.fresh_negative:
            found = self._eval_fresh_negative(
                rule_reviews, now,
                window_hours=int(params.get("window_hours", 2)),
                max_rating=int(params.get("max_rating", 2)),
            )
        elif rule.rule_type == AttentionRuleType.escalated:
            found = self._eval_escalated(rule_reviews)
        elif rule.rule_type == AttentionRuleType.rating_drop:
            found = self._rating_drops(
                rule_orgs, platform, snaps,
                threshold=float(params.get("threshold", -0.2)),
                top=int(params.get("top", 3)),
            )
        else:  # aspect_spike
            found = self._aspect_spikes(
                rule_reviews, now,
                min_recent=int(params.get("min_recent", 3)),
                top=int(params.get("top", 3)),
            )

        severity = rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity)
        for item in found:
            item["severity"] = severity
            item["rule_id"] = rule.id
            item["rule_name"] = rule.name
            if rule.name:
                item["subtitle"] = f"{rule.name} · {item['subtitle']}"
        return found

    @staticmethod
    def _eval_unanswered(reviews, now, *, hours: int) -> list[dict]:
        cutoff = now - timedelta(hours=hours)
        overdue = sum(1 for r in reviews if r.response_text is None and _aware(r.first_seen_at) <= cutoff)
        if not overdue:
            return []
        return [{
            "type": "unanswered_overdue",
            "title": f"{overdue} {_ru_plural(overdue, 'отзыв', 'отзыва', 'отзывов')} без ответа > {hours}ч",
            "subtitle": "SLA нарушен · риск эскалации",
            "value": overdue,
            "link": "/reviews",
        }]

    @staticmethod
    def _eval_fresh_negative(reviews, now, *, window_hours: int, max_rating: int) -> list[dict]:
        cutoff = now - timedelta(hours=window_hours)
        fresh = sum(1 for r in reviews if r.rating <= max_rating and _aware(r.first_seen_at) >= cutoff)
        if not fresh:
            return []
        return [{
            "type": "fresh_negative",
            "title": f"{fresh} "
            + _ru_plural(fresh, "новый негативный отзыв", "новых негативных отзыва", "новых негативных отзывов")
            + f" (1–{max_rating}★)",
            "subtitle": f"Поступили за последние {window_hours} "
            + _ru_plural(window_hours, "час", "часа", "часов"),
            "value": fresh,
            "link": "/reviews?rating=1",
        }]

    @staticmethod
    def _eval_escalated(reviews) -> list[dict]:
        escalated = sum(1 for r in reviews if r.status == ReviewStatus.escalated)
        if not escalated:
            return []
        return [{
            "type": "escalated",
            "title": f"{escalated} "
            + _ru_plural(escalated, "эскалированный отзыв ждёт", "эскалированных отзыва ждут", "эскалированных отзывов ждут")
            + " реакции",
            "subtitle": "Назначены маркетологу головного офиса",
            "value": escalated,
            "link": "/reviews?status=escalated",
        }]

    def _aspect_spikes(self, all_reviews, now, *, min_recent: int = 3, top: int = 3) -> list[dict]:
        recent_start = (now - timedelta(days=7)).date()
        prev_start = (now - timedelta(days=14)).date()
        recent: dict[str, int] = {}
        prev: dict[str, int] = {}
        for r in all_reviews:
            if not r.review_date or not r.problems:
                continue
            if r.review_date >= recent_start:
                bucket = recent
            elif r.review_date >= prev_start:
                bucket = prev
            else:
                continue
            for p in r.problems:
                cat = p.get("category")
                if cat:
                    bucket[cat] = bucket.get(cat, 0) + 1

        spikes = []
        for cat, rc in recent.items():
            pc = prev.get(cat, 0)
            if rc >= min_recent and rc > pc:
                change = round((rc - pc) / pc * 100) if pc else 100
                spikes.append((change, cat, rc))
        spikes.sort(reverse=True)
        return [
            {
                "type": "aspect_spike",
                "title": f"Рост упоминаний аспекта «{cat}»",
                "subtitle": f"+{change}% за 7 дней · {rc} {_ru_plural(rc, 'упоминание', 'упоминания', 'упоминаний')}",
                "value": change,
                "link": "/reviews",
            }
            for change, cat, rc in spikes[:top]
        ]

    def _rating_drops(self, orgs, platform, snaps, *, threshold: float = -0.2, top: int = 3) -> list[dict]:
        p = ReviewPlatform(platform) if platform != "all" else ReviewPlatform.yandex
        drops = []
        for org in orgs:
            delta = self._delta_for(org, p, snaps)
            if delta is not None and delta <= threshold:
                drops.append((delta, org))
        drops.sort(key=lambda d: d[0])
        return [
            {
                "type": "rating_drop",
                "title": f"Падение рейтинга: {org.name or 'без названия'}"
                + (f" ({org.city})" if org.city else ""),
                "subtitle": f"{round(delta, 2)} за период",
                "value": round(delta, 2),
                "link": f"/organizations/{org.id}",
            }
            for delta, org in drops[:top]
        ]
```

Differences from the old code, for review: `severity` is no longer emitted inside the per-type helpers (stamped from the rule in `_evaluate_rule`); `_eval_*` helpers are parameterized; titles interpolate the rule's thresholds.

- [ ] **Step 5: Seed default rules in the existing overview attention tests**

In `apps/api/tests/test_dashboard_overview.py` add a helper after `_review`:

```python
def _seed_rules(db):
    from app.services.attention_rule_service import AttentionRuleService
    AttentionRuleService(db).seed_defaults()
```

Call `_seed_rules(db_session)` as the first line in these tests (they now need rules to produce items): `test_attention_urgent_and_escalated`, `test_attention_aspect_spike`, `test_attention_rating_drop_needs_history`. `test_empty_network_zeroed_payload` stays unchanged (no orgs → empty payload before rules are consulted).

- [ ] **Step 6: Run tests to verify they pass**

From `apps/api`:
- `pytest tests/test_dashboard_attention_rules.py -v` — Expected: PASS.
- `pytest tests/test_dashboard_overview.py -v` — Expected: PASS.
- `pytest -v` — Expected: full suite green.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/dashboard_service.py apps/api/app/schemas/dashboard.py apps/api/tests/test_dashboard_overview.py apps/api/tests/test_dashboard_attention_rules.py
git commit -m "feat(api): rule-driven attention feed in dashboard overview"
```

---

### Task 6: Web types + API client functions

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`

**Interfaces:**
- Produces (types.ts): `AttentionRuleType`, `AttentionSeverity`, `AttentionScopeType` unions; `AttentionRule`, `AttentionRuleCreatePayload`, `AttentionRuleUpdatePayload` interfaces; `AttentionItem` gains `rule_id: string | null; rule_name: string | null;`.
- Produces (api.ts): `listAttentionRules(): Promise<AttentionRule[]>`, `createAttentionRule(payload)`, `updateAttentionRule(id, payload)`, `deleteAttentionRule(id)`.

- [ ] **Step 1: Add types**

In `apps/web/lib/types.ts`, extend `AttentionItem` (currently `types.ts:251-258`):

```ts
export interface AttentionItem {
  type: string;
  title: string;
  subtitle: string;
  value: number;
  severity: string;
  link: string;
  rule_id: string | null;
  rule_name: string | null;
}
```

After the dashboard section add:

```ts
// --- Правила блока «Требуют внимания» ---
export type AttentionRuleType =
  | "unanswered_overdue"
  | "fresh_negative"
  | "escalated"
  | "rating_drop"
  | "aspect_spike";

export type AttentionSeverity = "urgent" | "warn" | "info";

export type AttentionScopeType = "global" | "company" | "organizations";

export interface AttentionRule {
  id: string;
  rule_type: AttentionRuleType;
  name: string | null;
  is_enabled: boolean;
  severity: AttentionSeverity;
  params: Record<string, number>;
  scope_type: AttentionScopeType;
  company_id: string | null;
  organization_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface AttentionRuleCreatePayload {
  rule_type: AttentionRuleType;
  name?: string | null;
  is_enabled?: boolean;
  severity: AttentionSeverity;
  params?: Record<string, number>;
  scope_type?: AttentionScopeType;
  company_id?: string | null;
  organization_ids?: string[];
}

export type AttentionRuleUpdatePayload = Partial<Omit<AttentionRuleCreatePayload, "rule_type">>;
```

- [ ] **Step 2: Add API functions**

In `apps/web/lib/api.ts` add `AttentionRule`, `AttentionRuleCreatePayload`, `AttentionRuleUpdatePayload` to the type import block, then append:

```ts
// --- Правила внимания ---
export async function listAttentionRules(): Promise<AttentionRule[]> {
  const data = await request<{ items: AttentionRule[] }>("/api/attention-rules");
  return data.items;
}

export async function createAttentionRule(payload: AttentionRuleCreatePayload): Promise<AttentionRule> {
  return request<AttentionRule>("/api/attention-rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAttentionRule(
  id: string,
  payload: AttentionRuleUpdatePayload,
): Promise<AttentionRule> {
  return request<AttentionRule>(`/api/attention-rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAttentionRule(id: string): Promise<void> {
  await request<void>(`/api/attention-rules/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 3: Verify build**

From `apps/web`: `npm run lint`
Expected: clean (unused-import warnings acceptable only if the lint config already tolerates them — it does not, so nothing should be unused; the functions are exported, which satisfies the linter).

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts
git commit -m "feat(web): attention rule types and API client"
```

---

### Task 7: /attention-rules page + overview gear link

**Files:**
- Create: `apps/web/app/(dashboard)/attention-rules/page.tsx`
- Create: `apps/web/components/attention-rules/rule-form.tsx`
- Create: `apps/web/components/attention-rules/rules-table.tsx`
- Modify: `apps/web/components/shell/sidebar.tsx` (nav item)
- Modify: `apps/web/components/dashboard/attention-list.tsx` (gear link)

**Interfaces:**
- Consumes: API functions from Task 6, `listCompanies()`, `listOrganizations()` from `lib/api.ts`.
- Produces: client page at `/attention-rules`; `RuleForm({ companies, organizations, initial, onSubmit, onCancel })`; `RulesTable({ rules, companies, organizations, onToggle, onEdit, onDelete })`. Russian labels per type: `unanswered_overdue` → «Без ответа дольше N ч», `fresh_negative` → «Свежий негатив», `escalated` → «Эскалированные отзывы», `rating_drop` → «Падение рейтинга», `aspect_spike` → «Рост негативного аспекта».

- [ ] **Step 1: Shared label helpers + table component**

Create `apps/web/components/attention-rules/rules-table.tsx`:

```tsx
"use client";

import type { AttentionRule, AttentionRuleType, Company, Organization } from "@/lib/types";

export const RULE_TYPE_LABEL: Record<AttentionRuleType, string> = {
  unanswered_overdue: "Без ответа дольше порога",
  fresh_negative: "Свежий негатив",
  escalated: "Эскалированные отзывы",
  rating_drop: "Падение рейтинга",
  aspect_spike: "Рост негативного аспекта",
};

export const SEVERITY_LABEL: Record<string, string> = {
  urgent: "срочно",
  warn: "внимание",
  info: "инфо",
};

export function paramsSummary(rule: AttentionRule): string {
  const p = rule.params;
  switch (rule.rule_type) {
    case "unanswered_overdue":
      return `> ${p.hours ?? 24} ч без ответа`;
    case "fresh_negative":
      return `≤ ${p.max_rating ?? 2}★ за ${p.window_hours ?? 2} ч`;
    case "escalated":
      return "все эскалированные";
    case "rating_drop":
      return `Δ ≤ ${p.threshold ?? -0.2} · топ ${p.top ?? 3}`;
    case "aspect_spike":
      return `от ${p.min_recent ?? 3} упоминаний · топ ${p.top ?? 3}`;
  }
}

export function scopeSummary(
  rule: AttentionRule,
  companies: Company[],
  organizations: Organization[],
): string {
  if (rule.scope_type === "company") {
    const company = companies.find((c) => c.id === rule.company_id);
    return company ? `Компания: ${company.name}` : "Компания удалена";
  }
  if (rule.scope_type === "organizations") {
    const known = organizations.filter((o) => rule.organization_ids.includes(o.id));
    return `Организации: ${known.length || rule.organization_ids.length}`;
  }
  return "Вся сеть";
}

export function RulesTable({
  rules,
  companies,
  organizations,
  onToggle,
  onEdit,
  onDelete,
}: {
  rules: AttentionRule[];
  companies: Company[];
  organizations: Organization[];
  onToggle: (rule: AttentionRule, enabled: boolean) => void;
  onEdit: (rule: AttentionRule) => void;
  onDelete: (rule: AttentionRule) => void;
}) {
  if (rules.length === 0) {
    return <div className="py-10 text-center text-text-faint">Правил пока нет — создайте первое.</div>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-left text-xs uppercase text-text-faint">
          <th className="px-2 py-2">Тип</th>
          <th className="px-2 py-2">Название</th>
          <th className="px-2 py-2">Параметры</th>
          <th className="px-2 py-2">Скоуп</th>
          <th className="px-2 py-2">Серьёзность</th>
          <th className="px-2 py-2">Вкл</th>
          <th className="px-2 py-2" />
        </tr>
      </thead>
      <tbody>
        {rules.map((rule) => (
          <tr key={rule.id} className="border-b border-border/50" data-testid="rule-row">
            <td className="px-2 py-2 font-medium">{RULE_TYPE_LABEL[rule.rule_type]}</td>
            <td className="px-2 py-2 text-text-dim">{rule.name ?? "—"}</td>
            <td className="px-2 py-2 font-mono text-xs">{paramsSummary(rule)}</td>
            <td className="px-2 py-2">{scopeSummary(rule, companies, organizations)}</td>
            <td className="px-2 py-2">{SEVERITY_LABEL[rule.severity] ?? rule.severity}</td>
            <td className="px-2 py-2">
              <input
                type="checkbox"
                checked={rule.is_enabled}
                onChange={(e) => onToggle(rule, e.target.checked)}
                data-testid="rule-toggle"
              />
            </td>
            <td className="px-2 py-2 text-right">
              <button className="mr-2 text-xs text-accent" onClick={() => onEdit(rule)}>
                Изменить
              </button>
              <button className="text-xs text-bad" onClick={() => onDelete(rule)}>
                Удалить
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Rule form component**

Create `apps/web/components/attention-rules/rule-form.tsx`:

```tsx
"use client";

import { useState } from "react";
import type {
  AttentionRule,
  AttentionRuleCreatePayload,
  AttentionRuleType,
  AttentionScopeType,
  AttentionSeverity,
  Company,
  Organization,
} from "@/lib/types";
import { RULE_TYPE_LABEL } from "./rules-table";

// Дефолты параметров = сиды бэкенда.
const PARAM_DEFAULTS: Record<AttentionRuleType, Record<string, number>> = {
  unanswered_overdue: { hours: 24 },
  fresh_negative: { window_hours: 2, max_rating: 2 },
  escalated: {},
  rating_drop: { threshold: -0.2, top: 3 },
  aspect_spike: { min_recent: 3, top: 3 },
};

const PARAM_FIELDS: Record<AttentionRuleType, { key: string; label: string; step?: string }[]> = {
  unanswered_overdue: [{ key: "hours", label: "Часов без ответа" }],
  fresh_negative: [
    { key: "window_hours", label: "Окно, часов" },
    { key: "max_rating", label: "Макс. рейтинг (звёзд)" },
  ],
  escalated: [],
  rating_drop: [
    { key: "threshold", label: "Порог падения (отрицательный)", step: "0.05" },
    { key: "top", label: "Максимум точек в списке" },
  ],
  aspect_spike: [
    { key: "min_recent", label: "Мин. упоминаний за 7 дней" },
    { key: "top", label: "Максимум аспектов в списке" },
  ],
};

export function RuleForm({
  companies,
  organizations,
  initial,
  onSubmit,
  onCancel,
}: {
  companies: Company[];
  organizations: Organization[];
  initial: AttentionRule | null;
  onSubmit: (payload: AttentionRuleCreatePayload) => Promise<void>;
  onCancel: () => void;
}) {
  const [ruleType, setRuleType] = useState<AttentionRuleType>(initial?.rule_type ?? "unanswered_overdue");
  const [name, setName] = useState(initial?.name ?? "");
  const [severity, setSeverity] = useState<AttentionSeverity>(initial?.severity ?? "warn");
  const [scopeType, setScopeType] = useState<AttentionScopeType>(initial?.scope_type ?? "global");
  const [companyId, setCompanyId] = useState(initial?.company_id ?? "");
  const [orgIds, setOrgIds] = useState<string[]>(initial?.organization_ids ?? []);
  const [params, setParams] = useState<Record<string, number>>(
    initial?.params ?? PARAM_DEFAULTS[initial?.rule_type ?? "unanswered_overdue"],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function switchType(next: AttentionRuleType) {
    setRuleType(next);
    setParams(PARAM_DEFAULTS[next]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onSubmit({
        rule_type: ruleType,
        name: name.trim() || null,
        severity,
        params,
        scope_type: scopeType,
        company_id: scopeType === "company" ? companyId || null : null,
        organization_ids: scopeType === "organizations" ? orgIds : [],
      });
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        status === 401 || status === 403
          ? "Нужны права администратора"
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-border bg-surface-2 p-4" data-testid="rule-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Тип правила
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={ruleType}
            onChange={(e) => switchType(e.target.value as AttentionRuleType)}
            disabled={initial !== null}
            data-testid="rule-type"
          >
            {(Object.keys(RULE_TYPE_LABEL) as AttentionRuleType[]).map((t) => (
              <option key={t} value={t}>{RULE_TYPE_LABEL[t]}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Название (необязательно)
          <input
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            data-testid="rule-name"
          />
        </label>
      </div>

      {PARAM_FIELDS[ruleType].length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {PARAM_FIELDS[ruleType].map((field) => (
            <label key={field.key} className="block text-xs">
              {field.label}
              <input
                type="number"
                step={field.step ?? "1"}
                className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
                value={params[field.key] ?? ""}
                onChange={(e) => setParams({ ...params, [field.key]: Number(e.target.value) })}
                data-testid={`param-${field.key}`}
              />
            </label>
          ))}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Серьёзность
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={severity}
            onChange={(e) => setSeverity(e.target.value as AttentionSeverity)}
            data-testid="rule-severity"
          >
            <option value="urgent">срочно</option>
            <option value="warn">внимание</option>
            <option value="info">инфо</option>
          </select>
        </label>
        <label className="block text-xs">
          Скоуп
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={scopeType}
            onChange={(e) => setScopeType(e.target.value as AttentionScopeType)}
            data-testid="rule-scope"
          >
            <option value="global">Вся сеть</option>
            <option value="company">Компания</option>
            <option value="organizations">Организации</option>
          </select>
        </label>
      </div>

      {scopeType === "company" && (
        <label className="block text-xs">
          Компания
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
            data-testid="rule-company"
          >
            <option value="">— выберите —</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
      )}

      {scopeType === "organizations" && (
        <label className="block text-xs">
          Организации (Ctrl/Cmd — несколько)
          <select
            multiple
            size={Math.min(8, Math.max(3, organizations.length))}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={orgIds}
            onChange={(e) => setOrgIds(Array.from(e.target.selectedOptions, (o) => o.value))}
            data-testid="rule-orgs"
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>{o.name ?? o.id}</option>
            ))}
          </select>
        </label>
      )}

      {error && <div className="text-xs text-bad">{error}</div>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
          data-testid="rule-submit"
        >
          {initial ? "Сохранить" : "Создать правило"}
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-border px-3 py-1.5 text-xs">
          Отмена
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 3: Page**

Create `apps/web/app/(dashboard)/attention-rules/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createAttentionRule,
  deleteAttentionRule,
  listAttentionRules,
  listCompanies,
  listOrganizations,
  updateAttentionRule,
} from "@/lib/api";
import type { AttentionRule, AttentionRuleCreatePayload, Company, Organization } from "@/lib/types";
import { RuleForm } from "@/components/attention-rules/rule-form";
import { RulesTable } from "@/components/attention-rules/rules-table";

export default function AttentionRulesPage() {
  const [rules, setRules] = useState<AttentionRule[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [editing, setEditing] = useState<AttentionRule | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextRules, nextCompanies, nextOrgs] = await Promise.all([
      listAttentionRules(),
      listCompanies(),
      listOrganizations(),
    ]);
    setRules(nextRules);
    setCompanies(nextCompanies);
    setOrganizations(nextOrgs);
  }, []);

  useEffect(() => {
    refresh().catch((err) => setPageError((err as Error).message));
  }, [refresh]);

  async function handleSubmit(payload: AttentionRuleCreatePayload) {
    if (editing) {
      // rule_type менять нельзя — собираем update-пейлоад явно (без деструктуризации,
      // чтобы не ловить no-unused-vars на выброшенном поле).
      await updateAttentionRule(editing.id, {
        name: payload.name,
        severity: payload.severity,
        params: payload.params,
        scope_type: payload.scope_type,
        company_id: payload.company_id,
        organization_ids: payload.organization_ids,
      });
    } else {
      await createAttentionRule(payload);
    }
    setFormOpen(false);
    setEditing(null);
    await refresh();
  }

  async function handleToggle(rule: AttentionRule, enabled: boolean) {
    setPageError(null);
    try {
      await updateAttentionRule(rule.id, { is_enabled: enabled });
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setPageError(status === 401 || status === 403 ? "Нужны права администратора" : (err as Error).message);
    }
  }

  async function handleDelete(rule: AttentionRule) {
    if (!window.confirm("Удалить правило?")) return;
    setPageError(null);
    try {
      await deleteAttentionRule(rule.id);
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setPageError(status === 401 || status === 403 ? "Нужны права администратора" : (err as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Правила внимания</h1>
          <p className="text-sm text-text-dim">
            Управляют блоком «Требуют внимания» на обзоре сети
          </p>
        </div>
        <button
          className="rounded bg-accent px-3 py-2 text-xs font-semibold text-black"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          data-testid="rule-create"
        >
          + Новое правило
        </button>
      </div>

      {pageError && <div className="text-sm text-bad">{pageError}</div>}

      {formOpen && (
        <RuleForm
          companies={companies}
          organizations={organizations}
          initial={editing}
          onSubmit={handleSubmit}
          onCancel={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}

      <RulesTable
        rules={rules}
        companies={companies}
        organizations={organizations}
        onToggle={handleToggle}
        onEdit={(rule) => {
          setEditing(rule);
          setFormOpen(true);
        }}
        onDelete={handleDelete}
      />
    </div>
  );
}
```

- [ ] **Step 4: Sidebar + gear link**

In `apps/web/components/shell/sidebar.tsx` add after the `/jobs` item (`sidebar.tsx:23`):

```ts
      { href: "/attention-rules", label: "Правила внимания", icon: "⚡" },
```

In `apps/web/components/dashboard/attention-list.tsx` replace the single action link with a gear + existing link (keep the `Panel` API):

```tsx
      action={
        <div className="flex items-center gap-2">
          <Link
            href="/attention-rules"
            title="Настроить правила"
            aria-label="Настроить правила"
            className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] hover:bg-surface-3"
          >
            ⚙
          </Link>
          <Link href="/reviews" className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-[13px] hover:bg-surface-3">
            К отзывам →
          </Link>
        </div>
      }
```

- [ ] **Step 5: Verify lint/build**

From `apps/web`: `npm run lint`
Expected: clean. Then `npx tsc --noEmit` (if the project runs tsc separately) — clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/(dashboard)/attention-rules apps/web/components/attention-rules apps/web/components/shell/sidebar.tsx apps/web/components/dashboard/attention-list.tsx
git commit -m "feat(web): attention rules management page and overview gear link"
```

---

### Task 8: E2E spec + full verification gate

**Files:**
- Create: `apps/web/tests/attention-rules.spec.ts`

**Interfaces:**
- Consumes: page from Task 7, seeded admin creds via `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` (pattern from `apps/web/tests/overview.spec.ts:18-33`).

- [ ] **Step 1: Write the spec**

Create `apps/web/tests/attention-rules.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

// Attention rules management page. Auth-gated like the rest of the panel.

test("unauthenticated attention-rules redirects to login", async ({ page }) => {
  await page.goto("/attention-rules");
  await expect(page).toHaveURL(/\/login$/);
});

const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("attention rules page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
    await page.waitForURL(/\/companies$/);
  }

  test("renders the seeded rules list", async ({ page }) => {
    await login(page);
    await page.goto("/attention-rules");
    await expect(page.getByRole("heading", { name: "Правила внимания" })).toBeVisible();
    // 5 сид-правил из миграции 0015 (или больше, если оператор создавал свои).
    expect(await page.getByTestId("rule-row").count()).toBeGreaterThanOrEqual(5);
  });

  test("creates a rule and toggles it", async ({ page }) => {
    await login(page);
    await page.goto("/attention-rules");
    const before = await page.getByTestId("rule-row").count();

    await page.getByTestId("rule-create").click();
    await page.getByTestId("rule-name").fill("e2e-правило");
    await page.getByTestId("param-hours").fill("36");
    await page.getByTestId("rule-submit").click();

    await expect(page.getByText("e2e-правило")).toBeVisible();
    expect(await page.getByTestId("rule-row").count()).toBe(before + 1);

    const row = page.getByTestId("rule-row").filter({ hasText: "e2e-правило" });
    await row.getByTestId("rule-toggle").uncheck();
    await expect(row.getByTestId("rule-toggle")).not.toBeChecked();

    // Cleanup: удалить созданное правило, чтобы прогон был идемпотентным.
    page.once("dialog", (dialog) => dialog.accept());
    await row.getByRole("button", { name: "Удалить" }).click();
    await expect(page.getByText("e2e-правило")).toHaveCount(0);
  });

  test("gear link on overview leads here", async ({ page }) => {
    await login(page);
    await page.goto("/overview");
    await page.getByRole("link", { name: "Настроить правила" }).click();
    await expect(page).toHaveURL(/\/attention-rules$/);
  });
});
```

- [ ] **Step 2: Run the smoke test (no creds needed)**

From `apps/web`: `npx playwright test tests/attention-rules.spec.ts --grep "unauthenticated"`
Expected: PASS against a running web stack; if the stack is not running, note it and rely on the full gate below.

- [ ] **Step 3: Full verification gate**

- From `apps/api`: `pytest -v` — Expected: all pass.
- From `apps/web`: `npm run lint` — Expected: clean.
- From `apps/web` (with live stack + `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` if available): `npm run test:e2e` — Expected: pass (auth-gated tests skip without creds).

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/attention-rules.spec.ts
git commit -m "test(web): e2e coverage for attention rules page"
```

---

## Self-Review Notes

- Spec coverage: schema+seeds (Task 1), per-type params validation (Task 2), service CRUD + scope validation (Task 3), router + auth gates (Task 4), rule-driven `_attention` + `AttentionItem.rule_id/rule_name` + existing-test updates (Task 5), web types/api (Task 6), page + gear (Task 7), e2e (Task 8). "Вне скоупа" items untouched.
- Deploy note: production deploy must run `alembic upgrade head` (migration 0015) — the push-to-main deploy already does this per project setup; verify seeds exist after deploy (`GET /api/attention-rules` returns 5 items).
