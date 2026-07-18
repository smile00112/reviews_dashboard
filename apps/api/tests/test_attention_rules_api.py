"""CRUD contract + validation for /api/attention-rules (attention rules feature)."""

import uuid

import pytest
from pydantic import ValidationError

from app.models.attention_rule import AttentionRule
from app.models.company import Company
from app.models.organization import Organization
from app.models.enums import AttentionRuleType, AttentionScope, AttentionSeverity
from app.schemas.attention_rule import AttentionRuleCreate, AttentionRuleUpdate


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
