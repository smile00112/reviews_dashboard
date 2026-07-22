"""CRUD contract + validation + lifecycle for /api/attention-rules.

Feature 015 reworked the params (per-type time windows -> min_count) and added
period_days, the restart endpoint, and the firing-history endpoint.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.attention_event import AttentionEvent
from app.models.attention_rule import AttentionRule
from app.models.company import Company
from app.models.organization import Organization
from app.models.enums import (
    AttentionRuleType,
    AttentionScope,
    AttentionSeverity,
    ReviewPlatform,
    ReviewStatus,
    ScrapeMode,
)
from app.models.review import Review
from app.schemas.attention_rule import AttentionRuleCreate, AttentionRuleUpdate

NOW = datetime.now(timezone.utc)


def test_model_roundtrip_defaults(db_session):
    rule = AttentionRule(
        rule_type=AttentionRuleType.unanswered_overdue,
        severity=AttentionSeverity.urgent,
        params={"min_count": 1},
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
    assert rule.params == {"min_count": 1}
    # Feature 015 lifecycle defaults.
    assert rule.period_days == 1
    assert rule.window_started_at is not None
    assert rule.latched_at is None
    assert rule.is_latched is False
    assert rule.created_at is not None


def test_param_models_defaults_and_forbid_extra():
    from app.schemas.attention_rule import (
        PARAM_MODELS,
        FreshNegativeParams,
        RatingDropParams,
        UnansweredOverdueParams,
    )

    assert UnansweredOverdueParams().min_count == 1
    assert FreshNegativeParams().model_dump() == {"max_rating": 2, "min_count": 1}
    assert RatingDropParams().model_dump() == {"threshold": -0.2, "top": 3}
    assert set(PARAM_MODELS) == set(AttentionRuleType)

    with pytest.raises(ValidationError):
        UnansweredOverdueParams(min_count=0)         # ge=1
    with pytest.raises(ValidationError):
        FreshNegativeParams(max_rating=5)            # le=4
    with pytest.raises(ValidationError):
        RatingDropParams(threshold=0.1)              # lt=0
    with pytest.raises(ValidationError):
        UnansweredOverdueParams(min_count=1, bogus=1)  # extra="forbid"


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
        params={"max_rating": 3},
    ))
    # min_count дозаполнен дефолтом
    assert rule.params == {"max_rating": 3, "min_count": 1}
    assert rule.scope_type == AttentionScope.global_
    assert rule.period_days == 1
    assert rule.latched_at is None


def test_service_create_rejects_bad_params(db_session):
    from app.services.attention_rule_service import AttentionRuleValidationError
    svc = _make_service(db_session)
    with pytest.raises(AttentionRuleValidationError):
        svc.create(AttentionRuleCreate(
            rule_type=AttentionRuleType.unanswered_overdue,
            severity=AttentionSeverity.urgent,
            params={"min_count": 1, "bogus": 1},
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
    updated = svc.update(rule.id, AttentionRuleUpdate(params={"min_count": 2}, is_enabled=False))
    assert updated.params == {"min_count": 2}
    assert updated.is_enabled is False

    with pytest.raises(AttentionRuleValidationError):
        svc.update(rule.id, AttentionRuleUpdate(params={"window_hours": 1}))  # чужой ключ для типа

    assert svc.update(uuid.uuid4(), AttentionRuleUpdate(is_enabled=True)) is None


def test_service_update_period_days(db_session):
    svc = _make_service(db_session)
    rule = svc.create(AttentionRuleCreate(
        rule_type=AttentionRuleType.escalated, severity=AttentionSeverity.warn,
    ))
    assert rule.period_days == 1
    updated = svc.update(rule.id, AttentionRuleUpdate(period_days=7))
    assert updated.period_days == 7


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
    assert all(r.period_days == 1 for r in created)
    # Повторный вызов — no-op.
    assert svc.seed_defaults() == []
    assert len(svc.list_rules()) == 5


# --- HTTP contract ------------------------------------------------------------

def _payload(**over):
    base = {
        "rule_type": "unanswered_overdue",
        "severity": "urgent",
        "params": {"min_count": 1},
    }
    base.update(over)
    return base


def test_list_requires_session(client):
    assert client.get("/api/attention-rules").status_code == 401


def test_post_requires_auth(client):
    assert client.post("/api/attention-rules", json=_payload()).status_code == 401


def test_mutations_require_admin(operator_client):
    assert operator_client.post("/api/attention-rules", json=_payload()).status_code == 403
    fake_id = str(uuid.uuid4())
    assert operator_client.patch(f"/api/attention-rules/{fake_id}", json={"is_enabled": False}).status_code == 403
    assert operator_client.delete(f"/api/attention-rules/{fake_id}").status_code == 403
    assert operator_client.post(f"/api/attention-rules/{fake_id}/restart").status_code == 403


def test_crud_flow(admin_client):
    created = admin_client.post("/api/attention-rules", json=_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["rule_type"] == "unanswered_overdue"
    assert body["params"] == {"min_count": 1}
    assert body["scope_type"] == "global"
    # Feature 015 lifecycle fields present.
    assert body["period_days"] == 1
    assert body["is_latched"] is False
    assert body["latched_at"] is None
    assert body["window_started_at"] and body["period_ends_at"]
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


def test_period_days_default_and_validation(admin_client):
    # default 1 when omitted
    body = admin_client.post("/api/attention-rules", json=_payload()).json()
    assert body["period_days"] == 1

    # 0 / negative -> 422
    assert admin_client.post("/api/attention-rules", json=_payload(period_days=0)).status_code == 422
    assert admin_client.post("/api/attention-rules", json=_payload(period_days=-3)).status_code == 422

    # explicit + patch
    created = admin_client.post("/api/attention-rules", json=_payload(period_days=5)).json()
    assert created["period_days"] == 5
    patched = admin_client.patch(f"/api/attention-rules/{created['id']}", json={"period_days": 2})
    assert patched.status_code == 200
    assert patched.json()["period_days"] == 2


def test_create_invalid_params_422(admin_client):
    resp = admin_client.post("/api/attention-rules", json=_payload(params={"min_count": 1, "bogus": 1}))
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


# --- restart + history --------------------------------------------------------

def _escalated_org_with_review(db):
    org = Organization(name="Esc", rating=4.0, review_count=5)
    db.add(org)
    db.commit()
    db.refresh(org)
    r = Review(
        organization_id=org.id, source="yandex_maps", scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex, rating=1, review_text="плохо",
        content_hash="esc1", first_seen_at=NOW - timedelta(days=3), last_seen_at=NOW,
        status=ReviewStatus.escalated,
    )
    db.add(r)
    db.commit()
    return org


def test_restart_resets_and_reevaluates(admin_client, db_session):
    """escalated ignores the window, so restart fires deterministically (FR-022)."""
    _escalated_org_with_review(db_session)
    created = admin_client.post(
        "/api/attention-rules", json=_payload(rule_type="escalated", severity="warn", params={"min_count": 1})
    ).json()
    rule_id = created["id"]
    assert created["is_latched"] is False

    resp = admin_client.post(f"/api/attention-rules/{rule_id}/restart")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rule"]["is_latched"] is True
    assert body["rule"]["latched_at"] is not None
    assert len(body["events"]) == 1
    assert body["events"][0]["type"] == "escalated"
    assert body["events"][0]["value"] == 1


def test_restart_missing_404(admin_client):
    assert admin_client.post(f"/api/attention-rules/{uuid.uuid4()}/restart").status_code == 404


def test_events_history_and_cascade(admin_client, db_session):
    _escalated_org_with_review(db_session)
    rule_id = admin_client.post(
        "/api/attention-rules", json=_payload(rule_type="escalated", severity="warn", params={"min_count": 1})
    ).json()["id"]

    # never fired -> empty history
    assert admin_client.get(f"/api/attention-rules/{rule_id}/events").json()["items"] == []

    admin_client.post(f"/api/attention-rules/{rule_id}/restart")
    events = admin_client.get(f"/api/attention-rules/{rule_id}/events").json()["items"]
    assert len(events) == 1
    assert events[0]["rule_id"] == rule_id
    assert events[0]["fired_at"]

    # unknown rule -> 404
    assert admin_client.get(f"/api/attention-rules/{uuid.uuid4()}/events").status_code == 404

    # cascade: deleting the rule removes its events
    admin_client.delete(f"/api/attention-rules/{rule_id}")
    assert db_session.query(AttentionEvent).count() == 0


def test_events_history_requires_session(client):
    assert client.get(f"/api/attention-rules/{uuid.uuid4()}/events").status_code == 401
