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
