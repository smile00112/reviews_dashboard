from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity


# --- Параметры по типам правила (extra="forbid": лишний ключ = 422) ----------
# Feature 015: окно оценки = [window_started_at, now] заменяет встроенные окна
# типов, поэтому чисто-временные параметры (hours/window_hours) убраны; вместо
# них — min_count (порог счётчика в окне).

class UnansweredOverdueParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_count: int = Field(default=1, ge=1)


class FreshNegativeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_rating: int = Field(default=2, ge=1, le=4)
    min_count: int = Field(default=1, ge=1)


class EscalatedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_count: int = Field(default=1, ge=1)


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
    period_days: int = Field(default=1, ge=1)


class AttentionRuleUpdate(BaseModel):
    # rule_type менять нельзя — поля нет; params валидируются по типу правила в сервисе.
    name: str | None = Field(default=None, max_length=200)
    is_enabled: bool | None = None
    severity: AttentionSeverity | None = None
    params: dict | None = None
    scope_type: AttentionScope | None = None
    company_id: UUID | None = None
    organization_ids: list[UUID] | None = None
    period_days: int | None = Field(default=None, ge=1)


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
    period_days: int
    window_started_at: datetime
    latched_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_latched(self) -> bool:
        return self.latched_at is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def period_ends_at(self) -> datetime:
        return self.window_started_at + timedelta(days=self.period_days)


class AttentionRuleListResponse(BaseModel):
    items: list[AttentionRuleResponse]


# --- События (история срабатываний, feature 015) ------------------------------

class AttentionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_id: UUID
    fired_at: datetime
    type: AttentionRuleType
    severity: AttentionSeverity
    title: str
    subtitle: str | None
    value: float
    link: str


class AttentionEventListResponse(BaseModel):
    items: list[AttentionEventResponse]


class AttentionRuleRestartResponse(BaseModel):
    rule: AttentionRuleResponse
    events: list[AttentionEventResponse]
