"""Stateful evaluation of «Требуют внимания» rules (feature 015).

The block on /overview is no longer computed live per request. Instead a sweep
(APScheduler, every 30 min — see ``JobScheduler``) walks every enabled rule:

1. **Rollover** — if the current period has elapsed (``now >= window_started_at +
   period_days``), start a new period (``window_started_at = now``) and clear the
   latch. Applies whether or not the rule had fired.
2. **Evaluate if armed** — if ``latched_at IS NULL``, check the rule's condition
   over the window ``[window_started_at, now]`` (which *replaces* the old per-type
   2h/24h/7d windows). On a hit, latch the rule (``latched_at = now``) and append
   one ``AttentionEvent`` snapshot per emitted item.
3. A latched rule is skipped until its period elapses or it is restarted.

The same condition logic is reused by the admin restart endpoint. ``DashboardService``
reads the latched snapshots via ``current_block_items`` — it computes nothing.

Read-only over reviews/snapshots; writes only to app-owned tables (constitution
Principles II, VI).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.attention_event import AttentionEvent
from app.models.attention_rule import AttentionRule
from app.models.enums import AttentionRuleType, AttentionScope, ReviewPlatform, ReviewStatus
from app.models.organization import Organization
from app.models.review import Review
# Imported at module load: dashboard_service imports the evaluator only lazily
# (inside DashboardService.overview), so this direction has no cycle.
from app.services.dashboard_service import DashboardService, _aware, _ru_plural

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"urgent": 0, "warn": 1, "info": 2}

# rating_drop compares a single platform's rating column; with no page platform
# filter we keep the pre-015 default (Yandex).
_RATING_DROP_PLATFORM = ReviewPlatform.yandex

# Item = {type, title, subtitle, value, link, severity}
Item = dict


@dataclass
class RestartResult:
    rule: AttentionRule
    events: list[AttentionEvent] = field(default_factory=list)


class AttentionEvaluator:
    def __init__(self, db: Session, now_factory=None):
        self.db = db
        self._now_factory = now_factory or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ #
    # Public: sweep / restart / overview read                            #
    # ------------------------------------------------------------------ #
    def sweep(self, now: datetime | None = None) -> int:
        """Process every enabled rule once. Returns how many rules fired now.

        Each rule runs in its own transaction (row-locked): one rule's error is
        logged and isolated, the rest still process (FR-009).
        """
        now = now or self._now_factory()
        rule_ids = [
            r_id
            for (r_id,) in (
                self.db.query(AttentionRule.id)
                .filter(AttentionRule.is_enabled.is_(True))
                .order_by(AttentionRule.created_at, AttentionRule.id)
                .all()
            )
        ]
        fired = 0
        for rule_id in rule_ids:
            try:
                rule = (
                    self.db.query(AttentionRule)
                    .filter(AttentionRule.id == rule_id)
                    .with_for_update()
                    .first()
                )
                if rule is None or not rule.is_enabled:
                    continue
                if self._process_rule(rule, now):
                    fired += 1
                self.db.commit()
            except Exception:
                self.db.rollback()
                logger.exception("attention rule %s evaluation failed", rule_id)
        return fired

    def restart(self, rule_id: UUID, now: datetime | None = None) -> RestartResult | None:
        """Reset the rule's window and re-evaluate it synchronously (FR-022)."""
        now = now or self._now_factory()
        rule = (
            self.db.query(AttentionRule)
            .filter(AttentionRule.id == rule_id)
            .with_for_update()
            .first()
        )
        if rule is None:
            return None
        rule.window_started_at = now
        rule.latched_at = None
        events: list[AttentionEvent] = []
        if rule.is_enabled:
            items = self.evaluate_rule(rule, rule.window_started_at, now)
            if items:
                rule.latched_at = now
                events = self._emit_events(rule, items, now)
        self.db.commit()
        self.db.refresh(rule)
        for ev in events:
            self.db.refresh(ev)
        return RestartResult(rule=rule, events=events)

    def current_block_items(self) -> list[Item]:
        """Items for the /overview block: snapshots of currently-latched rules.

        Ignores all page filters (FR-019); ordered by severity then magnitude
        (FR-020). Reads stored events only — no per-review computation (FR-018).
        """
        rows = (
            self.db.query(AttentionEvent, AttentionRule.severity)
            .join(AttentionRule, AttentionRule.id == AttentionEvent.rule_id)
            .filter(
                AttentionRule.is_enabled.is_(True),
                AttentionRule.latched_at.isnot(None),
                AttentionEvent.fired_at == AttentionRule.latched_at,
            )
            .all()
        )
        items: list[Item] = [
            {
                "type": ev.type.value if hasattr(ev.type, "value") else str(ev.type),
                "title": ev.title,
                "subtitle": ev.subtitle,
                "value": ev.value,
                "link": ev.link,
                "severity": severity.value if hasattr(severity, "value") else str(severity),
            }
            for ev, severity in rows
        ]
        items.sort(key=lambda i: (_SEVERITY_ORDER.get(i["severity"], 9), -abs(i["value"])))
        return items

    # ------------------------------------------------------------------ #
    # Lifecycle step (rollover + latch)                                  #
    # ------------------------------------------------------------------ #
    def _process_rule(self, rule: AttentionRule, now: datetime) -> bool:
        window_end = _aware(rule.window_started_at) + timedelta(days=rule.period_days)
        if _aware(now) >= window_end:  # FR-005 rollover (fired or not)
            rule.window_started_at = now
            rule.latched_at = None
        if rule.latched_at is not None:  # FR-007 latched -> skip until rollover
            return False
        items = self.evaluate_rule(rule, rule.window_started_at, now)  # FR-006
        if not items:
            return False
        rule.latched_at = now
        self._emit_events(rule, items, now)
        return True

    def _emit_events(self, rule: AttentionRule, items: list[Item], now: datetime) -> list[AttentionEvent]:
        events: list[AttentionEvent] = []
        for item in items:
            ev = AttentionEvent(
                rule_id=rule.id,
                fired_at=now,
                type=rule.rule_type,
                severity=rule.severity,
                title=item["title"],
                subtitle=item.get("subtitle"),
                value=float(item["value"]),
                link=item["link"],
            )
            self.db.add(ev)
            events.append(ev)
        return events

    # ------------------------------------------------------------------ #
    # Condition evaluation over the window [window_start, now]            #
    # ------------------------------------------------------------------ #
    def evaluate_rule(self, rule: AttentionRule, window_start: datetime, now: datetime) -> list[Item]:
        params = rule.params or {}
        ws = _aware(window_start)
        nw = _aware(now)

        if rule.rule_type == AttentionRuleType.unanswered_overdue:
            min_count = int(params.get("min_count", 1))
            n = self._scoped_count(
                self._scope_ids_or_none(rule),
                Review.response_text.is_(None),
                Review.first_seen_at >= self._dt_param(ws),
                Review.first_seen_at <= self._dt_param(nw),
            )
            return self._eval_unanswered(n, min_count=min_count)

        if rule.rule_type == AttentionRuleType.fresh_negative:
            max_rating = int(params.get("max_rating", 2))
            min_count = int(params.get("min_count", 1))
            n = self._scoped_count(
                self._scope_ids_or_none(rule),
                Review.rating <= max_rating,
                Review.first_seen_at >= self._dt_param(ws),
                Review.first_seen_at <= self._dt_param(nw),
            )
            return self._eval_fresh_negative(n, max_rating=max_rating, min_count=min_count)

        if rule.rule_type == AttentionRuleType.escalated:
            min_count = int(params.get("min_count", 1))
            n = self._scoped_count(
                self._scope_ids_or_none(rule),
                Review.status == ReviewStatus.escalated,
            )
            return self._eval_escalated(n, min_count=min_count)

        if rule.rule_type == AttentionRuleType.rating_drop:
            return self._rating_drops(
                self._scope_orgs(rule), ws,
                threshold=float(params.get("threshold", -0.2)),
                top=int(params.get("top", 3)),
            )

        # aspect_spike
        return self._aspect_spikes(
            rule, ws, nw,
            min_recent=int(params.get("min_recent", 3)),
            top=int(params.get("top", 3)),
        )

    # ------------------------------------------------------------------ #
    # Per-type emitters                                                  #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _eval_unanswered(n: int, *, min_count: int) -> list[Item]:
        if n < min_count:
            return []
        return [{
            "type": "unanswered_overdue",
            "title": f"{n} {_ru_plural(n, 'отзыв', 'отзыва', 'отзывов')} без ответа",
            "subtitle": "SLA нарушен · риск эскалации",
            "value": n,
            "link": "/reviews",
        }]

    @staticmethod
    def _eval_fresh_negative(n: int, *, max_rating: int, min_count: int) -> list[Item]:
        if n < min_count:
            return []
        return [{
            "type": "fresh_negative",
            "title": f"{n} "
            + _ru_plural(n, "новый негативный отзыв", "новых негативных отзыва", "новых негативных отзывов")
            + f" (1–{max_rating}★)",
            "subtitle": "Поступили за текущий период",
            "value": n,
            "link": "/reviews?rating=1",
        }]

    @staticmethod
    def _eval_escalated(n: int, *, min_count: int) -> list[Item]:
        if n < min_count:
            return []
        return [{
            "type": "escalated",
            "title": f"{n} "
            + _ru_plural(n, "эскалированный отзыв ждёт", "эскалированных отзыва ждут", "эскалированных отзывов ждут")
            + " реакции",
            "subtitle": "Назначены маркетологу головного офиса",
            "value": n,
            "link": "/reviews?status=escalated",
        }]

    def _rating_drops(self, orgs, window_start: datetime, *, threshold: float, top: int) -> list[Item]:
        if not orgs:
            return []
        ds = DashboardService(self.db)
        snaps = ds._earliest_snapshot_ratings([o.id for o in orgs], window_start.date())
        drops = []
        for org in orgs:
            delta = ds._delta_for(org, _RATING_DROP_PLATFORM, snaps)
            if delta is not None and delta <= threshold:
                drops.append((delta, org))
        drops.sort(key=lambda d: d[0])
        return [
            {
                "type": "rating_drop",
                "title": f"Падение рейтинга: {org.name or 'без названия'}"
                + (f" ({org.city})" if org.city else ""),
                "subtitle": f"{round(delta, 2)} за период",
                "value": round(delta, 2),
                "link": f"/organizations/{org.id}",
            }
            for delta, org in drops[:top]
        ]

    def _aspect_spikes(
        self, rule: AttentionRule, window_start: datetime, now: datetime, *, min_recent: int, top: int
    ) -> list[Item]:
        period = timedelta(days=rule.period_days)
        recent_start = window_start.date()
        prev_start = (window_start - period).date()
        scope = self._scope_ids_or_none(rule)
        rows = (
            self.db.query(Review.review_date, Review.problems)
            .filter(
                *self._scoped_filters(scope),
                Review.review_date >= prev_start,
                Review.review_date <= now.date(),
                Review.problems.isnot(None),
            )
            .all()
        )
        recent: dict[str, int] = {}
        prev: dict[str, int] = {}
        for review_date, problems in rows:
            if not review_date or not problems:
                continue
            if review_date >= recent_start:
                bucket = recent
            elif review_date >= prev_start:
                bucket = prev
            else:
                continue
            for p in problems:
                cat = p.get("category")
                if cat:
                    bucket[cat] = bucket.get(cat, 0) + 1

        spikes = []
        for cat, rc in recent.items():
            pc = prev.get(cat, 0)
            if rc >= min_recent and rc > pc:
                change = round((rc - pc) / pc * 100) if pc else 100
                spikes.append((change, cat, rc))
        spikes.sort(reverse=True)
        return [
            {
                "type": "aspect_spike",
                "title": f"Рост упоминаний аспекта «{cat}»",
                "subtitle": f"+{change}% за период · {rc} {_ru_plural(rc, 'упоминание', 'упоминания', 'упоминаний')}",
                "value": change,
                "link": "/reviews",
            }
            for change, cat, rc in spikes[:top]
        ]

    # ------------------------------------------------------------------ #
    # Scope + count helpers                                              #
    # ------------------------------------------------------------------ #
    def _scope_orgs(self, rule: AttentionRule) -> list[Organization]:
        q = self.db.query(Organization)
        if rule.scope_type == AttentionScope.company:
            if rule.company_id is None:
                return []
            return q.filter(Organization.company_id == rule.company_id).all()
        if rule.scope_type == AttentionScope.organizations:
            ids: list[UUID] = []
            for raw in rule.organization_ids or []:
                try:
                    ids.append(UUID(str(raw)))
                except ValueError:
                    continue  # мусорный id (организация удалена) — игнорируем
            if not ids:
                return []
            return q.filter(Organization.id.in_(ids)).all()
        return q.all()  # global

    def _scope_ids_or_none(self, rule: AttentionRule) -> list[UUID] | None:
        """``None`` (global) drops the IN clause; company/organizations return an
        explicit id list (empty list -> matches nothing -> rule can't fire)."""
        if rule.scope_type == AttentionScope.global_:
            return None
        return [o.id for o in self._scope_orgs(rule)]

    @staticmethod
    def _scoped_filters(org_ids: list[UUID] | None) -> list:
        return [] if org_ids is None else [Review.organization_id.in_(org_ids)]

    def _scoped_count(self, org_ids: list[UUID] | None, *criteria) -> int:
        query = (
            self.db.query(func.count())
            .select_from(Review)
            .filter(*self._scoped_filters(org_ids), *criteria)
        )
        return int(query.scalar() or 0)

    def _dt_param(self, dt: datetime) -> datetime:
        """SQLite stores naive-UTC datetimes; strip tzinfo after normalizing to
        UTC. PostgreSQL ``timestamptz`` keeps aware."""
        if self.db.get_bind().dialect.name == "sqlite":
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
