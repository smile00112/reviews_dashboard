"""CRUD contract + validation for /api/attention-rules (attention rules feature)."""

import uuid

import pytest
from pydantic import ValidationError

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
