"""Network-level overview aggregation (feature 009).

Read-only. Aggregates already-collected reviews + organization metrics across a
selectable set of organizations, filtered by period / platform. Reuses the
deterministic local analytics (``analysis.analyzer.summarize``); introduces no
external inference (constitution Principle VI). Also owns the daily
``rating_snapshot`` capture/read used for period-over-period rating deltas.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analysis.analyzer import summarize
from app.core.config import settings
from app.models.attention_rule import AttentionRule
from app.models.enums import AttentionRuleType, AttentionScope, ReviewPlatform, ReviewStatus
from app.models.organization import Organization
from app.models.rating_snapshot import RatingSnapshot
from app.models.review import Review

# period token -> window length in days (None = all time)
PERIOD_DAYS: dict[str, int | None] = {
    "day": 1,
    "week": 7,
    "30d": 30,
    "90d": 90,
    "year": 365,
    "all": None,
}

# platform -> (org rating column, org review_count column)
_PLATFORM_COLS: dict[ReviewPlatform, tuple[str, str]] = {
    ReviewPlatform.yandex: ("rating", "review_count"),
    ReviewPlatform.gis2: ("gis2_rating", "gis2_review_count"),
    ReviewPlatform.google: ("google_rating", "google_review_count"),
}


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural agreement: pick(one, few, many) by count."""
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not 10 <= mod100 < 20:
        return few
    return many


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive timestamps (SQLite test backend) as UTC; Postgres is already aware."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # Rating snapshots (daily history for deltas)                         #
    # ------------------------------------------------------------------ #
    def capture_snapshot(
        self, organization_id: UUID, platform: ReviewPlatform, *, now: datetime | None = None
    ) -> None:
        """Upsert today's rating/review_count snapshot for one org+platform.

        Reads the platform-specific columns off the organization. Idempotent per
        day: a second capture on the same day overwrites (latest value wins).
        """
        now = now or datetime.now(timezone.utc)
        org = self.db.get(Organization, organization_id)
        if org is None:
            return
        rating_col, count_col = _PLATFORM_COLS[platform]
        rating = getattr(org, rating_col)
        review_count = getattr(org, count_col)
        captured_on = now.date()

        existing = (
            self.db.query(RatingSnapshot)
            .filter(
                RatingSnapshot.organization_id == organization_id,
                RatingSnapshot.platform == platform,
                RatingSnapshot.captured_on == captured_on,
            )
            .first()
        )
        if existing:
            existing.rating = rating
            existing.review_count = review_count
            existing.captured_at = now
        else:
            self.db.add(
                RatingSnapshot(
                    organization_id=organization_id,
                    platform=platform,
                    rating=rating,
                    review_count=review_count,
                    captured_on=captured_on,
                    captured_at=now,
                )
            )
        self.db.commit()

    def rating_delta(
        self, organization_id: UUID, platform: ReviewPlatform, period_start: date
    ) -> float | None:
        """Current rating minus the earliest snapshot on/after ``period_start``.

        Returns None when the org is gone, has no current rating, or no snapshot
        history covers the period (fresh install). Single-org convenience; the
        overview uses the batched ``_earliest_snapshot_ratings`` instead.
        """
        org = self.db.get(Organization, organization_id)
        if org is None:
            return None
        snaps = self._earliest_snapshot_ratings([organization_id], period_start)
        return self._delta_for(org, platform, snaps)

    def _earliest_snapshot_ratings(
        self, org_ids: list[UUID], period_start: date
    ) -> dict[tuple[UUID, ReviewPlatform], float]:
        """Earliest in-period snapshot rating per (org, platform) in ONE query
        (window function; supported by PG16 and SQLite >= 3.25)."""
        if not org_ids:
            return {}
        rn = (
            func.row_number()
            .over(
                partition_by=(RatingSnapshot.organization_id, RatingSnapshot.platform),
                order_by=RatingSnapshot.captured_on.asc(),
            )
            .label("rn")
        )
        subq = (
            self.db.query(
                RatingSnapshot.organization_id.label("organization_id"),
                RatingSnapshot.platform.label("platform"),
                RatingSnapshot.rating.label("rating"),
                rn,
            )
            .filter(
                RatingSnapshot.organization_id.in_(org_ids),
                RatingSnapshot.captured_on >= period_start,
                RatingSnapshot.rating.isnot(None),
            )
            .subquery()
        )
        rows = self.db.query(subq).filter(subq.c.rn == 1).all()
        return {(row.organization_id, row.platform): float(row.rating) for row in rows}

    @staticmethod
    def _delta_for(
        org: Organization,
        platform: ReviewPlatform,
        snaps: dict[tuple[UUID, ReviewPlatform], float],
    ) -> float | None:
        rating_col, _ = _PLATFORM_COLS[platform]
        current = getattr(org, rating_col)
        if current is None:
            return None
        base = snaps.get((org.id, platform))
        if base is None:
            return None
        return float(current) - base

    # ------------------------------------------------------------------ #
    # Filter base                                                        #
    # ------------------------------------------------------------------ #
    def _selected_orgs(self, org_ids: list[UUID] | None, company_id: UUID | None) -> list[Organization]:
        query = self.db.query(Organization)
        if company_id is not None:
            query = query.filter(Organization.company_id == company_id)
        if org_ids:
            query = query.filter(Organization.id.in_(org_ids))
        return query.all()

    def _review_query(self, org_ids: list[UUID], platform: str, *, cutoff: datetime | None):
        """Base filtered Review query (no period) restricted to selected orgs+platform."""
        query = self.db.query(Review).filter(Review.organization_id.in_(org_ids))
        if platform != "all":
            query = query.filter(Review.platform == ReviewPlatform(platform))
        return query

    # ------------------------------------------------------------------ #
    # Overview                                                           #
    # ------------------------------------------------------------------ #
    def overview(
        self,
        *,
        period: str = "30d",
        platform: str = "all",
        org_ids: list[UUID] | None = None,
        company_id: UUID | None = None,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc)
        days = PERIOD_DAYS.get(period, 30)
        cutoff = None if days is None else now - timedelta(days=days)
        period_start = (cutoff or now).date()

        orgs = self._selected_orgs(org_ids, company_id)
        selected_ids = [o.id for o in orgs]

        empty = self._empty_payload(period, platform, now)
        if not selected_ids:
            return empty

        base = self._review_query(selected_ids, platform, cutoff=cutoff)
        all_reviews = base.all()
        period_reviews = [r for r in all_reviews if cutoff is None or _aware(r.first_seen_at) >= cutoff]

        # One grouped query for all period-start snapshot baselines (no per-org N+1).
        snaps = self._earliest_snapshot_ratings(selected_ids, period_start)

        header = self._header(all_reviews, period_reviews, now)
        kpi_hero = self._kpi_hero(orgs, all_reviews, period_reviews, platform, snaps, days, now)
        kpi_strip = self._kpi_strip(period_reviews)
        rating_distribution = self._rating_distribution(period_reviews)
        sentiment = self._sentiment(period_reviews)
        platform_breakdown = self._platform_breakdown(orgs)
        platform_cards = self._platform_cards(orgs, selected_ids, cutoff, snaps, platform, all_reviews)
        attention = self._attention(orgs, all_reviews, platform, snaps, now)
        worst_locations = self._worst_locations(orgs, all_reviews, platform, snaps)
        trending_aspects = self._trending_aspects(all_reviews, now)

        return {
            **empty,
            "header": header,
            "kpi_hero": kpi_hero,
            "kpi_strip": kpi_strip,
            "rating_distribution": rating_distribution,
            "sentiment": sentiment,
            "platform_breakdown": platform_breakdown,
            "platform_cards": platform_cards,
            "attention": attention,
            "worst_locations": worst_locations,
            "trending_aspects": trending_aspects,
        }

    # ------------------------------------------------------------------ #
    # Blocks                                                             #
    # ------------------------------------------------------------------ #
    def _header(self, all_reviews, period_reviews, now: datetime) -> dict:
        cutoff_24h = now - timedelta(hours=24)
        cutoff_2h = now - timedelta(hours=2)
        return {
            "new_in_period": len(period_reviews),
            "unanswered_over_24h": sum(
                1 for r in all_reviews if r.response_text is None and _aware(r.first_seen_at) <= cutoff_24h
            ),
            "fresh_negatives_2h": sum(
                1 for r in all_reviews if r.rating <= 2 and _aware(r.first_seen_at) >= cutoff_2h
            ),
        }

    def _kpi_hero(self, orgs, all_reviews, period_reviews, platform, snaps, days, now) -> dict:
        # Weighted network average rating over the platform's org columns.
        avg_rating = self._weighted_avg_rating(orgs, platform)
        delta = self._network_rating_delta(orgs, platform, snaps)

        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        new_today = sum(1 for r in all_reviews if _aware(r.first_seen_at) >= today_start)
        cutoff_24h = now - timedelta(hours=24)
        unanswered = [r for r in all_reviews if r.response_text is None]

        span = days or max(1, self._span_days(all_reviews, now))
        return {
            "network_avg_rating": avg_rating,
            "network_avg_rating_delta": delta,
            "new_in_period": len(period_reviews),
            "new_today": new_today,
            "total_reviews": len(all_reviews),
            "avg_per_day": round(len(period_reviews) / span, 1) if span else 0.0,
            "unanswered_total": len(unanswered),
            "unanswered_delta_24h": sum(1 for r in unanswered if _aware(r.first_seen_at) >= cutoff_24h),
            "overdue_24h": sum(1 for r in unanswered if _aware(r.first_seen_at) <= cutoff_24h),
        }

    def _kpi_strip(self, period_reviews) -> dict:
        minutes = [
            (_aware(r.response_first_seen_at) - _aware(r.first_seen_at)).total_seconds() / 60
            for r in period_reviews
            if r.response_first_seen_at is not None
        ]
        sla_threshold = settings.overview_sla_threshold_minutes
        sla_percent = (
            round(sum(1 for m in minutes if m <= sla_threshold) / len(minutes) * 100, 1)
            if minutes
            else None
        )

        rated = [r for r in period_reviews if r.rating is not None]
        n = len(rated)
        reputation = None
        if n:
            share5 = sum(1 for r in rated if r.rating == 5) / n * 100
            share13 = sum(1 for r in rated if r.rating <= 3) / n * 100
            reputation = round(share5 - share13, 1)

        summary = summarize(
            {
                "sentiment": r.sentiment,
                "sentiment_score": r.sentiment_score,
                "problems": r.problems,
                "rating_sentiment_mismatch": r.rating_sentiment_mismatch,
            }
            for r in period_reviews
        )

        return {
            "response_avg_min": round(sum(minutes) / len(minutes)) if minutes else None,
            "response_median_min": round(median(minutes)) if minutes else None,
            "response_p95_min": self._percentile(minutes, 95) if minutes else None,
            "response_approximate": True,
            "sla_percent": sla_percent,
            "positivity_percent": summary["sentiment_percent"]["positive"],
            "reputation_index": reputation,
        }

    def _rating_distribution(self, period_reviews) -> dict:
        rated = [r for r in period_reviews if r.rating is not None]
        total = len(rated)
        counts = {star: sum(1 for r in rated if r.rating == star) for star in (5, 4, 3, 2, 1)}

        def pct(n: int) -> float:
            return round(n / total * 100, 1) if total else 0.0

        bars = [{"star": star, "count": counts[star], "percent": pct(counts[star])} for star in (5, 4, 3, 2, 1)]
        share_4_5 = pct(counts[5] + counts[4])
        share_1_3 = pct(counts[3] + counts[2] + counts[1])
        return {"bars": bars, "share_4_5": share_4_5, "share_1_3": share_1_3, "total": total}

    def _sentiment(self, period_reviews) -> dict:
        summary = summarize(
            {
                "sentiment": r.sentiment,
                "sentiment_score": r.sentiment_score,
                "problems": r.problems,
                "rating_sentiment_mismatch": r.rating_sentiment_mismatch,
            }
            for r in period_reviews
        )
        dist = summary["sentiment_distribution"]
        pct = summary["sentiment_percent"]
        return {
            "positive": dist["positive"],
            "neutral": dist["neutral"],
            "negative": dist["negative"],
            "positive_percent": pct["positive"],
            "neutral_percent": pct["neutral"],
            "negative_percent": pct["negative"],
            "analyzed_total": summary["analyzed_reviews"],
        }

    def _platform_breakdown(self, orgs) -> list[dict]:
        """Review-count distribution per platform from operator/scraped org columns."""
        out = []
        for p in _PLATFORM_COLS:
            _, count_col = _PLATFORM_COLS[p]
            total = sum(getattr(o, count_col) or 0 for o in orgs)
            out.append({"platform": p.value, "review_count": total})
        return out

    def _platform_cards(self, orgs, selected_ids, cutoff, snaps, platform, all_reviews) -> list[dict]:
        # Per-platform review-derived metrics (negativity, response speed) computed
        # from actual review rows, ignoring the platform filter so every card is
        # comparable. Google has no review rows -> those fields stay None.
        if platform == "all":
            # already materialized platform-agnostic in overview(); no second scan
            rows = all_reviews
        else:
            rows = self.db.query(Review).filter(Review.organization_id.in_(selected_ids)).all()
        reviews = [r for r in rows if cutoff is None or _aware(r.first_seen_at) >= cutoff]
        by_platform: dict[ReviewPlatform, list] = {p: [] for p in _PLATFORM_COLS}
        for r in reviews:
            if r.platform in by_platform:
                by_platform[r.platform].append(r)

        cards = []
        for p in _PLATFORM_COLS:
            prs = by_platform[p]
            negativity = None
            response_hours = None
            if prs:
                rated = [r for r in prs if r.rating is not None]
                if rated:
                    negativity = round(sum(1 for r in rated if r.rating <= 2) / len(rated) * 100, 1)
                mins = [
                    (_aware(r.response_first_seen_at) - _aware(r.first_seen_at)).total_seconds() / 3600
                    for r in prs
                    if r.response_first_seen_at is not None
                ]
                if mins:
                    response_hours = round(sum(mins) / len(mins), 1)
            cards.append(
                {
                    "platform": p.value,
                    "weighted_rating": self._weighted_avg_rating(orgs, p.value),
                    "rating_delta": self._network_rating_delta(orgs, p.value, snaps),
                    "negativity_percent": negativity,
                    "response_speed_hours": response_hours,
                }
            )
        return cards

    # ------------------------------------------------------------------ #
    # Attention feed — управляется правилами attention_rules              #
    # ------------------------------------------------------------------ #
    _SEVERITY_ORDER = {"urgent": 0, "warn": 1, "info": 2}

    def _attention(self, orgs, all_reviews, platform, snaps, now) -> list[dict]:
        rules = (
            self.db.query(AttentionRule)
            .filter(AttentionRule.is_enabled.is_(True))
            .order_by(AttentionRule.created_at)
            .all()
        )
        items: list[dict] = []
        for rule in rules:
            scope_ids = self._rule_scope_ids(rule, orgs)
            if not scope_ids:
                continue  # скоуп не пересекается с фильтрами страницы
            rule_orgs = [o for o in orgs if o.id in scope_ids]
            rule_reviews = [r for r in all_reviews if r.organization_id in scope_ids]
            items.extend(self._evaluate_rule(rule, rule_orgs, rule_reviews, platform, snaps, now))
        # Внутри severity — по модулю value: у rating_drop value отрицательный,
        # худшее падение должно стоять первым, как и самый большой счётчик.
        items.sort(key=lambda i: (self._SEVERITY_ORDER.get(i["severity"], 9), -abs(i["value"])))
        return items

    @staticmethod
    def _rule_scope_ids(rule: AttentionRule, orgs) -> set[UUID]:
        selected = {o.id for o in orgs}
        if rule.scope_type == AttentionScope.company:
            return {o.id for o in orgs if o.company_id == rule.company_id}
        if rule.scope_type == AttentionScope.organizations:
            wanted: set[UUID] = set()
            for raw in rule.organization_ids or []:
                try:
                    wanted.add(UUID(str(raw)))
                except ValueError:
                    continue  # мусорный id (организация удалена) — игнорируем
            return selected & wanted
        return selected

    def _evaluate_rule(self, rule, rule_orgs, rule_reviews, platform, snaps, now) -> list[dict]:
        params = rule.params or {}
        if rule.rule_type == AttentionRuleType.unanswered_overdue:
            found = self._eval_unanswered(rule_reviews, now, hours=int(params.get("hours", 24)))
        elif rule.rule_type == AttentionRuleType.fresh_negative:
            found = self._eval_fresh_negative(
                rule_reviews, now,
                window_hours=int(params.get("window_hours", 2)),
                max_rating=int(params.get("max_rating", 2)),
            )
        elif rule.rule_type == AttentionRuleType.escalated:
            found = self._eval_escalated(rule_reviews)
        elif rule.rule_type == AttentionRuleType.rating_drop:
            found = self._rating_drops(
                rule_orgs, platform, snaps,
                threshold=float(params.get("threshold", -0.2)),
                top=int(params.get("top", 3)),
            )
        else:  # aspect_spike
            found = self._aspect_spikes(
                rule_reviews, now,
                min_recent=int(params.get("min_recent", 3)),
                top=int(params.get("top", 3)),
            )

        severity = rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity)
        for item in found:
            item["severity"] = severity
            item["rule_id"] = rule.id
            item["rule_name"] = rule.name
            if rule.name:
                item["subtitle"] = f"{rule.name} · {item['subtitle']}"
        return found

    @staticmethod
    def _eval_unanswered(reviews, now, *, hours: int) -> list[dict]:
        cutoff = now - timedelta(hours=hours)
        overdue = sum(1 for r in reviews if r.response_text is None and _aware(r.first_seen_at) <= cutoff)
        if not overdue:
            return []
        return [{
            "type": "unanswered_overdue",
            "title": f"{overdue} {_ru_plural(overdue, 'отзыв', 'отзыва', 'отзывов')} без ответа > {hours}ч",
            "subtitle": "SLA нарушен · риск эскалации",
            "value": overdue,
            "link": "/reviews",
        }]

    @staticmethod
    def _eval_fresh_negative(reviews, now, *, window_hours: int, max_rating: int) -> list[dict]:
        cutoff = now - timedelta(hours=window_hours)
        fresh = sum(1 for r in reviews if r.rating <= max_rating and _aware(r.first_seen_at) >= cutoff)
        if not fresh:
            return []
        return [{
            "type": "fresh_negative",
            "title": f"{fresh} "
            + _ru_plural(fresh, "новый негативный отзыв", "новых негативных отзыва", "новых негативных отзывов")
            + f" (1–{max_rating}★)",
            "subtitle": f"Поступили за последние {window_hours} "
            + _ru_plural(window_hours, "час", "часа", "часов"),
            "value": fresh,
            "link": "/reviews?rating=1",
        }]

    @staticmethod
    def _eval_escalated(reviews) -> list[dict]:
        escalated = sum(1 for r in reviews if r.status == ReviewStatus.escalated)
        if not escalated:
            return []
        return [{
            "type": "escalated",
            "title": f"{escalated} "
            + _ru_plural(escalated, "эскалированный отзыв ждёт", "эскалированных отзыва ждут", "эскалированных отзывов ждут")
            + " реакции",
            "subtitle": "Назначены маркетологу головного офиса",
            "value": escalated,
            "link": "/reviews?status=escalated",
        }]

    def _aspect_spikes(self, all_reviews, now, *, min_recent: int = 3, top: int = 3) -> list[dict]:
        recent_start = (now - timedelta(days=7)).date()
        prev_start = (now - timedelta(days=14)).date()
        recent: dict[str, int] = {}
        prev: dict[str, int] = {}
        for r in all_reviews:
            if not r.review_date or not r.problems:
                continue
            if r.review_date >= recent_start:
                bucket = recent
            elif r.review_date >= prev_start:
                bucket = prev
            else:
                continue
            for p in r.problems:
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
                "subtitle": f"+{change}% за 7 дней · {rc} {_ru_plural(rc, 'упоминание', 'упоминания', 'упоминаний')}",
                "value": change,
                "link": "/reviews",
            }
            for change, cat, rc in spikes[:top]
        ]

    def _rating_drops(self, orgs, platform, snaps, *, threshold: float = -0.2, top: int = 3) -> list[dict]:
        p = ReviewPlatform(platform) if platform != "all" else ReviewPlatform.yandex
        drops = []
        for org in orgs:
            delta = self._delta_for(org, p, snaps)
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

    # ------------------------------------------------------------------ #
    # Worst locations + trending aspects                                 #
    # ------------------------------------------------------------------ #
    def _worst_locations(self, orgs, all_reviews, platform, snaps, *, top: int = 10) -> list[dict]:
        p = ReviewPlatform(platform) if platform != "all" else ReviewPlatform.yandex
        rating_col, _ = _PLATFORM_COLS[p]

        unanswered_by_org: dict = {}
        for r in all_reviews:
            if r.response_text is None:
                unanswered_by_org[r.organization_id] = unanswered_by_org.get(r.organization_id, 0) + 1

        rows = []
        for org in orgs:
            rating = getattr(org, rating_col)
            if rating is None:
                continue
            rows.append({
                "organization_id": str(org.id),
                "city": org.city,
                "name": org.name,
                "rating": round(float(rating), 2),
                "rating_delta": self._delta_for(org, p, snaps),
                "unanswered_count": unanswered_by_org.get(org.id, 0),
            })
        rows.sort(key=lambda r: r["rating"])
        return rows[:top]

    def _trending_aspects(self, all_reviews, now, *, top: int = 8) -> list[dict]:
        recent_start = (now - timedelta(days=7)).date()
        prev_start = (now - timedelta(days=14)).date()
        recent: dict[str, int] = {}
        prev: dict[str, int] = {}
        sentiment: dict[str, dict[str, int]] = {}
        for r in all_reviews:
            if not r.review_date or not r.problems:
                continue
            if r.review_date >= recent_start:
                bucket = recent
                track_sentiment = True
            elif r.review_date >= prev_start:
                bucket = prev
                track_sentiment = False
            else:
                continue
            for pr in r.problems:
                cat = pr.get("category")
                if not cat:
                    continue
                bucket[cat] = bucket.get(cat, 0) + 1
                if track_sentiment:
                    s = sentiment.setdefault(cat, {"pos": 0, "neu": 0, "neg": 0})
                    if r.sentiment == "positive":
                        s["pos"] += 1
                    elif r.sentiment == "negative":
                        s["neg"] += 1
                    else:
                        s["neu"] += 1

        aspects = []
        for cat, rc in recent.items():
            pc = prev.get(cat, 0)
            change = round((rc - pc) / pc * 100) if pc else None
            aspects.append({
                "category": cat,
                "mentions": rc,
                "change_percent": change,
                "sentiment": sentiment.get(cat, {"pos": 0, "neu": 0, "neg": 0}),
            })
        aspects.sort(key=lambda a: a["mentions"], reverse=True)
        return aspects[:top]

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _weighted_avg_rating(self, orgs, platform: str) -> float | None:
        platforms = (
            [ReviewPlatform(platform)] if platform != "all" else list(_PLATFORM_COLS.keys())
        )
        num = 0.0
        den = 0
        for org in orgs:
            for p in platforms:
                rating_col, count_col = _PLATFORM_COLS[p]
                rating = getattr(org, rating_col)
                count = getattr(org, count_col) or 0
                if rating is not None and count:
                    num += float(rating) * count
                    den += count
        return round(num / den, 2) if den else None

    def _network_rating_delta(self, orgs, platform: str, snaps) -> float | None:
        p = ReviewPlatform(platform) if platform != "all" else ReviewPlatform.yandex
        deltas = [self._delta_for(org, p, snaps) for org in orgs]
        deltas = [d for d in deltas if d is not None]
        return round(sum(deltas) / len(deltas), 2) if deltas else None

    @staticmethod
    def _span_days(reviews, now) -> int:
        stamps = [_aware(r.first_seen_at) for r in reviews if r.first_seen_at]
        if not stamps:
            return 1
        earliest = min(stamps)
        return max(1, (now - earliest).days)

    @staticmethod
    def _percentile(values: list[float], pct: int) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        k = (len(ordered) - 1) * (pct / 100)
        f = int(k)
        c = min(f + 1, len(ordered) - 1)
        val = ordered[f] + (ordered[c] - ordered[f]) * (k - f)
        return round(val)

    def _empty_payload(self, period: str, platform: str, now: datetime) -> dict:
        return {
            "period": period,
            "platform": platform,
            "generated_at": now,
            "header": {"new_in_period": 0, "unanswered_over_24h": 0, "fresh_negatives_2h": 0},
            "kpi_hero": {
                "network_avg_rating": None,
                "network_avg_rating_delta": None,
                "new_in_period": 0,
                "new_today": 0,
                "total_reviews": 0,
                "avg_per_day": 0.0,
                "unanswered_total": 0,
                "unanswered_delta_24h": 0,
                "overdue_24h": 0,
            },
            "kpi_strip": {
                "response_avg_min": None,
                "response_median_min": None,
                "response_p95_min": None,
                "response_approximate": True,
                "sla_percent": None,
                "positivity_percent": 0.0,
                "reputation_index": None,
            },
            "rating_distribution": {"bars": [], "share_4_5": 0.0, "share_1_3": 0.0, "total": 0},
            "sentiment": {
                "positive": 0, "neutral": 0, "negative": 0,
                "positive_percent": 0.0, "neutral_percent": 0.0, "negative_percent": 0.0,
                "analyzed_total": 0,
            },
            "platform_breakdown": [],
            "platform_cards": [],
            "attention": [],
            "worst_locations": [],
            "trending_aspects": [],
        }
