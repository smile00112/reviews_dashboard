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
