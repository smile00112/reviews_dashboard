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
