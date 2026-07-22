"""Feature 015: condition evaluation over the [window_started_at, now] window,
plus sweep idempotency / disabled-skip / error isolation.

The scheduler is off under pytest; we drive AttentionEvaluator.sweep(now=...)
directly with an injected clock.
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


def _org(db, name="Org", rating=4.5, company_id=None):
    org = Organization(name=name, rating=rating, review_count=10, company_id=company_id)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, rating=4, first_seen, hash_, response_text=None,
            status=ReviewStatus.new, review_date=None, problems=None):
    r = Review(
        organization_id=org.id, source="yandex_maps", scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex, rating=rating, review_text="text",
        response_text=response_text, status=status, review_date=review_date,
        problems=problems, content_hash=hash_, first_seen_at=first_seen, last_seen_at=first_seen,
    )
    db.add(r)
    db.commit()
    return r


def _rule(db, rule_type, *, params=None, severity=AttentionSeverity.urgent, **over):
    payload = {"rule_type": rule_type, "severity": severity, "params": params or {}}
    payload.update(over)
    return AttentionRuleService(db).create(AttentionRuleCreate(**payload))


def _arm(db, rule, *, days_ago, period_days=30):
    """Anchor the rule's window `days_ago` in the past with a period long enough
    that the sweep does not immediately roll it over."""
    rule.window_started_at = NOW - timedelta(days=days_ago)
    rule.period_days = period_days
    rule.latched_at = None
    db.commit()


def _fire(db, rule):
    """Evaluate a single rule now, latch if it hits; return created events."""
    ev = AttentionEvaluator(db)
    fired_before = db.query(AttentionEvent).count()
    ev.sweep(now=NOW)
    db.refresh(rule)
    return db.query(AttentionEvent).count() - fired_before


# --- unanswered_overdue ------------------------------------------------------

def test_unanswered_counts_only_in_window_and_min_count(db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(days=2), hash_="in")     # in window
    _review(db_session, org, first_seen=NOW - timedelta(days=40), hash_="old")   # before window
    rule = _rule(db_session, AttentionRuleType.unanswered_overdue, params={"min_count": 1})
    _arm(db_session, rule, days_ago=5)

    assert _fire(db_session, rule) == 1
    assert rule.is_latched
    ev = db_session.query(AttentionEvent).one()
    assert ev.type == AttentionRuleType.unanswered_overdue
    assert ev.value == 1  # only the in-window review


def test_unanswered_respects_min_count(db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(days=1), hash_="a")
    rule = _rule(db_session, AttentionRuleType.unanswered_overdue, params={"min_count": 2})
    _arm(db_session, rule, days_ago=5)
    assert _fire(db_session, rule) == 0
    assert not rule.is_latched


def test_answered_review_not_counted(db_session):
    org = _org(db_session)
    _review(db_session, org, first_seen=NOW - timedelta(days=1), hash_="a", response_text="ответ")
    rule = _rule(db_session, AttentionRuleType.unanswered_overdue, params={"min_count": 1})
    _arm(db_session, rule, days_ago=5)
    assert _fire(db_session, rule) == 0


# --- fresh_negative ----------------------------------------------------------

def test_fresh_negative_window_and_rating(db_session):
    org = _org(db_session)
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(days=1), hash_="neg")
    _review(db_session, org, rating=5, first_seen=NOW - timedelta(days=1), hash_="pos")   # not negative
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(days=40), hash_="old")  # out of window
    rule = _rule(db_session, AttentionRuleType.fresh_negative, params={"max_rating": 2, "min_count": 1})
    _arm(db_session, rule, days_ago=5)
    assert _fire(db_session, rule) == 1
    assert db_session.query(AttentionEvent).one().value == 1


# --- escalated (window ignored) ----------------------------------------------

def test_escalated_ignores_window(db_session):
    org = _org(db_session)
    # first_seen far before the window — still counts (no status timestamp).
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(days=100), hash_="esc",
            status=ReviewStatus.escalated)
    rule = _rule(db_session, AttentionRuleType.escalated, severity=AttentionSeverity.warn,
                 params={"min_count": 1})
    _arm(db_session, rule, days_ago=1, period_days=30)
    assert _fire(db_session, rule) == 1
    assert db_session.query(AttentionEvent).one().type == AttentionRuleType.escalated


# --- rating_drop (baseline at window_start) ----------------------------------

def test_rating_drop_uses_window_start_baseline(db_session):
    from app.services.dashboard_service import DashboardService

    org = _org(db_session, rating=4.5)
    DashboardService(db_session).capture_snapshot(
        org.id, ReviewPlatform.yandex, now=NOW - timedelta(days=20)
    )
    org.rating = 4.2  # current dropped
    db_session.commit()
    rule = _rule(db_session, AttentionRuleType.rating_drop, severity=AttentionSeverity.warn,
                 params={"threshold": -0.2, "top": 3})
    _arm(db_session, rule, days_ago=10, period_days=30)
    assert _fire(db_session, rule) == 1
    ev = db_session.query(AttentionEvent).one()
    assert ev.type == AttentionRuleType.rating_drop
    assert ev.value <= -0.2


# --- aspect_spike (window vs preceding equal-length window) -------------------

def test_aspect_spike_window_vs_previous(db_session):
    org = _org(db_session)
    today = NOW.date()
    for i in range(4):  # recent bucket
        _review(db_session, org, rating=3, first_seen=NOW - timedelta(days=1),
                review_date=today - timedelta(days=1), problems=[{"category": "опоздание"}], hash_=f"r{i}")
    _review(db_session, org, rating=3, first_seen=NOW - timedelta(days=8),  # previous bucket
            review_date=today - timedelta(days=8), problems=[{"category": "опоздание"}], hash_="p0")
    rule = _rule(db_session, AttentionRuleType.aspect_spike, severity=AttentionSeverity.warn,
                 params={"min_recent": 3, "top": 3})
    _arm(db_session, rule, days_ago=3, period_days=7)
    assert _fire(db_session, rule) == 1
    ev = db_session.query(AttentionEvent).one()
    assert "опоздание" in ev.title


# --- sweep semantics ---------------------------------------------------------

def test_sweep_idempotent_no_duplicate_events(db_session):
    org = _org(db_session)
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(days=1), hash_="neg",
            status=ReviewStatus.escalated)
    rule = _rule(db_session, AttentionRuleType.escalated, severity=AttentionSeverity.warn,
                 params={"min_count": 1})
    _arm(db_session, rule, days_ago=1, period_days=30)

    ev = AttentionEvaluator(db_session)
    assert ev.sweep(now=NOW) == 1
    assert ev.sweep(now=NOW + timedelta(minutes=10)) == 0  # still latched
    assert db_session.query(AttentionEvent).count() == 1


def test_sweep_skips_disabled_rule(db_session):
    org = _org(db_session)
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(days=1), hash_="neg",
            status=ReviewStatus.escalated)
    rule = _rule(db_session, AttentionRuleType.escalated, severity=AttentionSeverity.warn,
                 params={"min_count": 1}, is_enabled=False)
    _arm(db_session, rule, days_ago=1, period_days=30)
    assert AttentionEvaluator(db_session).sweep(now=NOW) == 0
    assert db_session.query(AttentionEvent).count() == 0


def test_sweep_isolates_one_rule_failure(db_session, monkeypatch):
    org = _org(db_session)
    _review(db_session, org, rating=1, first_seen=NOW - timedelta(days=1), hash_="esc",
            status=ReviewStatus.escalated)
    rule_a = _rule(db_session, AttentionRuleType.escalated, severity=AttentionSeverity.warn,
                   params={"min_count": 1}, name="A")
    rule_b = _rule(db_session, AttentionRuleType.escalated, severity=AttentionSeverity.warn,
                   params={"min_count": 1}, name="B")
    _arm(db_session, rule_a, days_ago=1, period_days=30)
    _arm(db_session, rule_b, days_ago=1, period_days=30)

    from app.services import attention_evaluator as mod
    original = mod.AttentionEvaluator.evaluate_rule

    def boom(self, rule, ws, now):
        if rule.id == rule_a.id:
            raise RuntimeError("boom")
        return original(self, rule, ws, now)

    monkeypatch.setattr(mod.AttentionEvaluator, "evaluate_rule", boom)
    mod.AttentionEvaluator(db_session).sweep(now=NOW)

    db_session.refresh(rule_a)
    db_session.refresh(rule_b)
    assert rule_a.latched_at is None      # failed rule not latched
    assert rule_b.latched_at is not None  # other rule still fired
