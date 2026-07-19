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
