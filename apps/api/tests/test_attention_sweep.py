"""Feature 015: rule lifecycle across sweep ticks — rollover, latch, restart.

Escalated rules are window-independent, so they re-fire whenever armed; that
makes them the cleanest probe for the ARMED<->LATCHED state machine.
"""

from datetime import datetime, timedelta, timezone

from app.models.attention_event import AttentionEvent
from app.models.enums import (
    AttentionRuleType,
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

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _org(db):
    org = Organization(name="Org", rating=4.5, review_count=10)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _escalated_review(db, org, hash_="esc"):
    r = Review(
        organization_id=org.id, source="yandex_maps", scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex, rating=1, review_text="плохо",
        content_hash=hash_, first_seen_at=NOW - timedelta(days=3), last_seen_at=NOW,
        status=ReviewStatus.escalated,
    )
    db.add(r)
    db.commit()
    return r


def _escalated_rule(db, *, period_days=1, window_at=NOW):
    rule = AttentionRuleService(db).create(AttentionRuleCreate(
        rule_type=AttentionRuleType.escalated, severity=AttentionSeverity.warn,
        params={"min_count": 1}, period_days=period_days,
    ))
    rule.window_started_at = window_at
    rule.latched_at = None
    db.commit()
    return rule


def test_fire_then_rollover_refires_next_period(db_session):
    org = _org(db_session)
    _escalated_review(db_session, org)
    rule = _escalated_rule(db_session, period_days=1, window_at=NOW)
    ev = AttentionEvaluator(db_session)

    assert ev.sweep(now=NOW) == 1
    db_session.refresh(rule)
    first_latch = rule.latched_at
    assert first_latch is not None

    # Past the period -> rollover to a new window, latch cleared, re-fire.
    later = NOW + timedelta(days=1, hours=1)
    assert ev.sweep(now=later) == 1
    db_session.refresh(rule)
    assert rule.latched_at is not None and rule.latched_at != first_latch
    assert db_session.query(AttentionEvent).count() == 2


def test_latched_not_reevaluated_within_period(db_session):
    org = _org(db_session)
    _escalated_review(db_session, org)
    rule = _escalated_rule(db_session, period_days=5, window_at=NOW)
    ev = AttentionEvaluator(db_session)

    assert ev.sweep(now=NOW) == 1
    # Still inside the period -> skipped, no new event.
    assert ev.sweep(now=NOW + timedelta(days=2)) == 0
    assert db_session.query(AttentionEvent).count() == 1

    # After the period -> rollover + re-fire.
    assert ev.sweep(now=NOW + timedelta(days=6)) == 1
    assert db_session.query(AttentionEvent).count() == 2


def test_never_fired_window_rolls_forward(db_session):
    # No escalated reviews -> rule never fires, but its window must still advance
    # so it does not grow without bound.
    _org(db_session)
    rule = _escalated_rule(db_session, period_days=1, window_at=NOW)
    ev = AttentionEvaluator(db_session)

    assert ev.sweep(now=NOW) == 0
    later = NOW + timedelta(days=1, hours=2)
    assert ev.sweep(now=later) == 0
    db_session.refresh(rule)
    # window advanced to ~the later sweep time, not still anchored at NOW.
    assert rule.window_started_at.replace(tzinfo=timezone.utc) >= NOW + timedelta(days=1)
    assert rule.latched_at is None


def test_restart_resets_window_and_reevaluates(db_session):
    org = _org(db_session)
    _escalated_review(db_session, org)
    rule = _escalated_rule(db_session, period_days=30, window_at=NOW)
    ev = AttentionEvaluator(db_session)

    assert ev.sweep(now=NOW) == 1
    assert db_session.query(AttentionEvent).count() == 1

    # Within the (30d) period a plain sweep would skip; restart forces re-eval now.
    result = ev.restart(rule.id, now=NOW + timedelta(days=1))
    assert result is not None
    assert result.rule.latched_at is not None
    assert len(result.events) == 1
    db_session.refresh(rule)
    assert rule.window_started_at.replace(tzinfo=timezone.utc) == NOW + timedelta(days=1)
    assert db_session.query(AttentionEvent).count() == 2


def test_restart_unknown_rule_returns_none(db_session):
    import uuid
    assert AttentionEvaluator(db_session).restart(uuid.uuid4(), now=NOW) is None
