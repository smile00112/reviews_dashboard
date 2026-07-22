"""Feature 015: the /overview attention block reads latched snapshots produced
by the sweep — it no longer computes anything live, and ignores page filters.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.company import Company
from app.models.enums import (
    AttentionRuleType,
    AttentionScope,
    AttentionSeverity,
    ReviewPlatform,
    ReviewStatus,
    ScrapeMode,
)
from app.models.organization import Organization
from app.models.review import Review
from app.schemas.attention_rule import AttentionRuleCreate
from app.services.attention_evaluator import AttentionEvaluator
from app.services.attention_rule_service import AttentionRuleService

NOW = datetime.now(timezone.utc)


def _org(db, name="Org", company_id=None, rating=4.5):
    org = Organization(name=name, rating=rating, review_count=10, company_id=company_id)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, rating=4, first_seen, hash_, status=ReviewStatus.new):
    r = Review(
        organization_id=org.id, source="yandex_maps", scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex, rating=rating, review_text="text",
        content_hash=hash_, first_seen_at=first_seen, last_seen_at=first_seen, status=status,
    )
    db.add(r)
    db.commit()
    return r


def _rule(db, **over):
    payload = {
        "rule_type": AttentionRuleType.unanswered_overdue,
        "severity": AttentionSeverity.urgent,
        "params": {"min_count": 1},
    }
    payload.update(over)
    rule = AttentionRuleService(db).create(AttentionRuleCreate(**payload))
    # Anchor an open window covering the seeded reviews.
    rule.window_started_at = NOW - timedelta(days=5)
    rule.period_days = 30
    rule.latched_at = None
    db.commit()
    return rule


def _sweep(db):
    AttentionEvaluator(db).sweep(now=NOW)


def _attention(admin_client, query=""):
    return admin_client.get(f"/api/dashboard/overview?period=30d{query}").json()["attention"]


def test_no_latched_rules_empty_feed(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    # No sweep run yet -> block empty even though a matching rule exists.
    _rule(db_session)
    assert _attention(admin_client) == []


def test_sweep_latches_and_block_reads_snapshot(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(hours=1), hash_="h2")
    _rule(db_session)  # unanswered_overdue
    _rule(db_session, rule_type=AttentionRuleType.fresh_negative,
          params={"max_rating": 2, "min_count": 1})
    _sweep(db_session)

    items = _attention(admin_client)
    types = {i["type"] for i in items}
    assert "unanswered_overdue" in types
    assert "fresh_negative" in types


def test_disabled_rule_produces_nothing(admin_client, db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    _rule(db_session, is_enabled=False)
    _sweep(db_session)
    assert _attention(admin_client) == []


def test_company_scope_counts_only_company_orgs(admin_client, db_session):
    company = Company(name="Сеть")
    db_session.add(company)
    db_session.commit()
    inside = _org(db_session, name="In", company_id=company.id)
    outside = _org(db_session, name="Out")
    _review(db_session, inside, first_seen=NOW - timedelta(hours=48), hash_="in1")
    _review(db_session, outside, first_seen=NOW - timedelta(hours=48), hash_="out1")

    _rule(db_session, scope_type=AttentionScope.company, company_id=company.id)
    _sweep(db_session)
    items = _attention(admin_client)
    assert len(items) == 1
    assert items[0]["value"] == 1  # только inside


def test_org_scope_and_stale_org_id_ignored(admin_client, db_session):
    target = _org(db_session, name="Target")
    other = _org(db_session, name="Other")
    _review(db_session, target, first_seen=NOW - timedelta(hours=48), hash_="t1")
    _review(db_session, other, first_seen=NOW - timedelta(hours=48), hash_="o1")

    rule = _rule(db_session, scope_type=AttentionScope.organizations, organization_ids=[target.id])
    # Мусорный id (после удаления организации) игнорируется молча.
    rule.organization_ids = [str(target.id), str(uuid.uuid4())]
    db_session.commit()
    _sweep(db_session)

    items = _attention(admin_client)
    assert len(items) == 1
    assert items[0]["value"] == 1  # только target


def test_block_ignores_page_filters(admin_client, db_session):
    """FR-019: a latched global rule shows regardless of period/platform/org filters."""
    org = _org(db_session)
    other = _org(db_session, name="Other")
    _review(db_session, org, first_seen=NOW - timedelta(hours=48), hash_="h1")
    _rule(db_session)
    _sweep(db_session)

    base = _attention(admin_client)
    assert len(base) == 1
    # Filtering the page to a different org, another platform, a shorter period —
    # the block is unchanged.
    assert _attention(admin_client, query=f"&org_ids={other.id}") == base
    assert _attention(admin_client, query="&platform=gis2") == base
    assert admin_client.get(
        f"/api/dashboard/overview?period=day"
    ).json()["attention"] == base


def test_same_severity_sorted_by_magnitude(admin_client, db_session):
    from app.services.dashboard_service import DashboardService

    org_small = _org(db_session, name="Small")
    org_big = _org(db_session, name="Big")
    old = NOW - timedelta(days=20)
    for org, before, after in ((org_small, 4.5, 4.2), (org_big, 4.7, 4.2)):
        org.rating = before
        db_session.commit()
        DashboardService(db_session).capture_snapshot(org.id, ReviewPlatform.yandex, now=old)
        org.rating = after
        db_session.commit()

    _rule(db_session, rule_type=AttentionRuleType.rating_drop,
          severity=AttentionSeverity.warn, params={"threshold": -0.2, "top": 3})
    _sweep(db_session)

    items = _attention(admin_client)
    drops = [i for i in items if i["type"] == "rating_drop"]
    assert len(drops) == 2
    assert abs(drops[0]["value"]) >= abs(drops[1]["value"])  # худшее падение первым
