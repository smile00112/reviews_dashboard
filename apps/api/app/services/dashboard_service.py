"""Network-level overview aggregation (feature 009).

Read-only. Aggregates already-collected reviews + organization metrics across a
selectable set of organizations, filtered by period / platform. Counts and
distributions are computed by the database (feature 012); only the small
per-review slices that genuinely need row data (response delays, 14-day
problem aspects) are loaded, and never ``review_text``. Sentiment percents
reproduce ``analysis.analyzer.summarize`` semantics exactly; no external
inference (constitution Principle VI). Also owns the daily ``rating_snapshot``
capture/read used for period-over-period rating deltas.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from uuid import UUID

from sqlalchemy import Float, and_, case, cast, func
from sqlalchemy.orm import Session

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

    def _dt_param(self, dt: datetime) -> datetime:
        """Bind-safe cutoff: SQLite stores naive-UTC datetime strings, so strip
        tzinfo after normalizing to UTC; PostgreSQL ``timestamptz`` keeps aware."""
        if self.db.get_bind().dialect.name == "sqlite":
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def _scoped_filters(org_ids: list[UUID] | None, platform: str) -> list:
        """``org_ids=None`` means "every organization" — the IN clause is then
        omitted (a 600-element UUID list costs more than the scan it guards)."""
        filters = [] if org_ids is None else [Review.organization_id.in_(org_ids)]
        if platform != "all":
            filters.append(Review.platform == ReviewPlatform(platform))
        return filters

    # ------------------------------------------------------------------ #
    # Aggregate queries (feature 012 — no full review materialization)   #
    # ------------------------------------------------------------------ #
    def _review_cube(self, org_ids: list[UUID] | None, cutoff: datetime | None, now: datetime) -> list:
        """One scan of the scoped reviews, grouped by (platform, rating, sentiment).

        Every counter, distribution and response-delay figure the overview needs is
        folded out of this single result: period membership and the 24h/2h/today
        windows are conditional aggregates rather than separate scans. Always
        platform-agnostic (platform cards need every platform); consumers narrow to
        the page platform in Python.
        """
        delay = self._response_delay_expr()
        answered = Review.response_first_seen_at.isnot(None)
        sla_seconds = settings.overview_sla_threshold_minutes * 60
        fs = Review.first_seen_at
        unanswered = Review.response_text.is_(None)
        in_period = True if cutoff is None else fs >= self._dt_param(cutoff)
        cutoff_24h = self._dt_param(now - timedelta(hours=24))
        cutoff_2h = self._dt_param(now - timedelta(hours=2))
        today_start = self._dt_param(datetime(now.year, now.month, now.day, tzinfo=timezone.utc))

        def cnt(*conds):
            return func.count(case((and_(*conds), 1)))

        query = self.db.query(
            Review.platform,
            Review.rating,
            Review.sentiment,
            func.count().label("total"),
            (func.count() if cutoff is None else cnt(in_period)).label("count"),
            cnt(fs >= today_start).label("new_today"),
            cnt(Review.rating <= 2, fs >= cutoff_2h).label("fresh_negatives_2h"),
            cnt(unanswered).label("unanswered_total"),
            cnt(unanswered, fs <= cutoff_24h).label("overdue_24h"),
            cnt(unanswered, fs >= cutoff_24h).label("unanswered_delta_24h"),
            func.min(fs).label("min_first_seen"),
            cnt(in_period, answered).label("response_count"),
            func.sum(case((and_(in_period, answered), delay))).label("response_sum_seconds"),
            cnt(in_period, answered, delay <= sla_seconds).label("within_sla"),
        ).filter(*self._scoped_filters(org_ids, "all"))
        return query.group_by(Review.platform, Review.rating, Review.sentiment).all()

    @staticmethod
    def _counters_from_cube(cube, page_platforms) -> dict:
        """Header/KPI counters folded out of the cube, narrowed to the page platform."""
        keys = (
            "total",
            "count",
            "new_today",
            "fresh_negatives_2h",
            "unanswered_total",
            "overdue_24h",
            "unanswered_delta_24h",
        )
        totals = {k: 0 for k in keys}
        earliest = None
        for row in cube:
            if page_platforms is not None and row.platform not in page_platforms:
                continue
            for k in keys:
                totals[k] += getattr(row, k)
            if row.min_first_seen is not None and (earliest is None or row.min_first_seen < earliest):
                earliest = row.min_first_seen
        totals["new_in_period"] = totals.pop("count")
        totals["min_first_seen"] = earliest
        return totals

    @staticmethod
    def _sentiment_counts_from_cube(cube, page_platforms) -> dict:
        counts: dict = {}
        for row in cube:
            if page_platforms is not None and row.platform not in page_platforms:
                continue
            counts[row.sentiment] = counts.get(row.sentiment, 0) + row.count
        return counts

    @staticmethod
    def _response_stats_from_cube(cube) -> dict:
        stats: dict = {}
        for row in cube:
            entry = stats.setdefault(row.platform, {"count": 0, "sum_seconds": 0.0, "within_sla": 0})
            entry["count"] += row.response_count
            entry["sum_seconds"] += float(row.response_sum_seconds or 0.0)
            entry["within_sla"] += row.within_sla
        return stats

    def _unanswered_by_org(self, org_ids: list[UUID] | None, platform: str) -> dict[UUID, int]:
        query = self.db.query(Review.organization_id, func.count()).filter(
            *self._scoped_filters(org_ids, platform), Review.response_text.is_(None)
        )
        return dict(query.group_by(Review.organization_id).all())

    def _response_delay_expr(self):
        """Response delay in seconds, computed by the database (avoids shipping
        two timestamps per row and parsing them in Python)."""
        if self.db.get_bind().dialect.name == "sqlite":
            return (
                func.julianday(Review.response_first_seen_at) - func.julianday(Review.first_seen_at)
            ) * 86400.0
        # extract() yields NUMERIC on PostgreSQL — cast so consumers always get float
        return cast(
            func.extract("epoch", Review.response_first_seen_at - Review.first_seen_at), Float
        )

    def _response_base(self, org_ids: list[UUID] | None, cutoff: datetime | None):
        """Filtered query base over period rows carrying a response (platform-agnostic)."""
        filters = [Review.response_first_seen_at.isnot(None)]
        if org_ids is not None:
            filters.append(Review.organization_id.in_(org_ids))
        if cutoff is not None:
            filters.append(Review.first_seen_at >= self._dt_param(cutoff))
        return filters

    def _response_percentiles(
        self, org_ids: list[UUID] | None, cutoff: datetime | None, platform: str
    ) -> tuple[float | None, float | None]:
        """(median, p95) response delay in seconds for the page's platform scope.

        PostgreSQL computes them with ``percentile_cont`` (linear interpolation —
        the same definition as ``statistics.median`` and ``_percentile``); SQLite,
        which lacks it, falls back to loading the delays.
        """
        delay = self._response_delay_expr()
        filters = list(self._response_base(org_ids, cutoff))
        if platform != "all":
            filters.append(Review.platform == ReviewPlatform(platform))

        if self.db.get_bind().dialect.name == "sqlite":
            values = [v for (v,) in self.db.query(delay).select_from(Review).filter(*filters)]
            if not values:
                return None, None
            return median(values), self._percentile(values, 95)

        row = (
            self.db.query(
                func.percentile_cont(0.5).within_group(delay.asc()).label("median"),
                func.percentile_cont(0.95).within_group(delay.asc()).label("p95"),
            )
            .select_from(Review)
            .filter(*filters)
            .one()
        )
        if row.median is None:
            return None, None
        return float(row.median), float(row.p95)

    def _aspect_rows(self, org_ids: list[UUID], platform: str, now: datetime) -> list:
        """14-day rows with problems for trending aspects / aspect-spike rules."""
        prev_start = (now - timedelta(days=14)).date()
        return (
            self.db.query(Review.organization_id, Review.review_date, Review.problems, Review.sentiment)
            .filter(
                *self._scoped_filters(org_ids, platform),
                Review.review_date >= prev_start,
                Review.problems.isnot(None),
            )
            .all()
        )

    def _scoped_count(self, org_ids: list[UUID], platform: str, *criteria) -> int:
        query = (
            self.db.query(func.count())
            .select_from(Review)
            .filter(*self._scoped_filters(org_ids, platform), *criteria)
        )
        return int(query.scalar() or 0)

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

        # One grouped query for all period-start snapshot baselines (no per-org N+1).
        snaps = self._earliest_snapshot_ratings(selected_ids, period_start)

        # No org/company filter -> every organization is selected, so the review
        # queries can drop the (potentially 600-element) IN clause entirely.
        scope = None if (not org_ids and company_id is None) else selected_ids

        page_platforms = None if platform == "all" else {ReviewPlatform(platform)}

        cube = self._review_cube(scope, cutoff, now)
        counters = self._counters_from_cube(cube, page_platforms)
        rating_counts = cube
        sentiment_counts = self._sentiment_counts_from_cube(cube, page_platforms)
        response_stats = self._response_stats_from_cube(cube)
        unanswered_by_org = self._unanswered_by_org(scope, platform)
        response_percentiles = self._response_percentiles(scope, cutoff, platform)
        aspect_rows = self._aspect_rows(scope, platform, now)

        header = self._header(counters)
        kpi_hero = self._kpi_hero(orgs, counters, platform, snaps, days, now)
        kpi_strip = self._kpi_strip(
            response_stats, response_percentiles, rating_counts, sentiment_counts, page_platforms
        )
        rating_distribution = self._rating_distribution(rating_counts, page_platforms)
        sentiment = self._sentiment(sentiment_counts)
        platform_breakdown = self._platform_breakdown(orgs)
        platform_cards = self._platform_cards(orgs, snaps, rating_counts, response_stats)
        attention = self._attention(orgs, platform, snaps, now, aspect_rows, scope)
        worst_locations = self._worst_locations(orgs, platform, snaps, unanswered_by_org)
        trending_aspects = self._trending_aspects(aspect_rows, now)

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
    def _header(self, counters: dict) -> dict:
        return {
            "new_in_period": counters["new_in_period"],
            "unanswered_over_24h": counters["overdue_24h"],
            "fresh_negatives_2h": counters["fresh_negatives_2h"],
        }

    def _kpi_hero(self, orgs, counters, platform, snaps, days, now) -> dict:
        # Weighted network average rating over the platform's org columns.
        avg_rating = self._weighted_avg_rating(orgs, platform)
        delta = self._network_rating_delta(orgs, platform, snaps)

        span = days or max(1, self._span_days(counters["min_first_seen"], now))
        new_in_period = counters["new_in_period"]
        return {
            "network_avg_rating": avg_rating,
            "network_avg_rating_delta": delta,
            "new_in_period": new_in_period,
            "new_today": counters["new_today"],
            "total_reviews": counters["total"],
            "avg_per_day": round(new_in_period / span, 1) if span else 0.0,
            "unanswered_total": counters["unanswered_total"],
            "unanswered_delta_24h": counters["unanswered_delta_24h"],
            "overdue_24h": counters["overdue_24h"],
        }

    def _kpi_strip(
        self, response_stats, percentiles, rating_counts, sentiment_counts, page_platforms
    ) -> dict:
        count = sum_seconds = within_sla = 0
        for p, stats in response_stats.items():
            if page_platforms is not None and p not in page_platforms:
                continue
            count += stats["count"]
            sum_seconds += stats["sum_seconds"]
            within_sla += stats["within_sla"]
        sla_percent = round(within_sla / count * 100, 1) if count else None
        median_seconds, p95_seconds = percentiles

        n = share5_count = share13_count = 0
        for row in rating_counts:
            if page_platforms is not None and row.platform not in page_platforms:
                continue
            if row.rating is None:
                continue
            n += row.count
            if row.rating == 5:
                share5_count += row.count
            if row.rating <= 3:
                share13_count += row.count
        reputation = None
        if n:
            share5 = share5_count / n * 100
            share13 = share13_count / n * 100
            reputation = round(share5 - share13, 1)

        _, sentiment_percent, _ = self._sentiment_summary(sentiment_counts)

        return {
            "response_avg_min": round(sum_seconds / count / 60) if count else None,
            "response_median_min": round(median_seconds / 60) if median_seconds is not None else None,
            "response_p95_min": round(p95_seconds / 60) if p95_seconds is not None else None,
            "response_approximate": True,
            "sla_percent": sla_percent,
            "positivity_percent": sentiment_percent["positive"],
            "reputation_index": reputation,
        }

    def _rating_distribution(self, rating_counts, page_platforms) -> dict:
        counts = {star: 0 for star in (5, 4, 3, 2, 1)}
        total = 0
        for row in rating_counts:
            if page_platforms is not None and row.platform not in page_platforms:
                continue
            if row.rating is None:
                continue
            total += row.count
            if row.rating in counts:
                counts[row.rating] += row.count

        def pct(n: int) -> float:
            return round(n / total * 100, 1) if total else 0.0

        bars = [{"star": star, "count": counts[star], "percent": pct(counts[star])} for star in (5, 4, 3, 2, 1)]
        share_4_5 = pct(counts[5] + counts[4])
        share_1_3 = pct(counts[3] + counts[2] + counts[1])
        return {"bars": bars, "share_4_5": share_4_5, "share_1_3": share_1_3, "total": total}

    @staticmethod
    def _sentiment_summary(sentiment_counts: dict) -> tuple[dict, dict, int]:
        """Distribution/percent/analyzed-count with the exact semantics of
        ``analysis.analyzer.summarize``: falsy sentiment = unanalyzed; unknown
        labels count toward ``analyzed`` but no bucket; pct = round(x/n*100, 1)."""
        distribution = {"positive": 0, "negative": 0, "neutral": 0}
        analyzed = 0
        for label, count in sentiment_counts.items():
            if not label:
                continue
            analyzed += count
            if label in distribution:
                distribution[label] += count
        percent = {
            k: (round(v / analyzed * 100, 1) if analyzed else 0.0) for k, v in distribution.items()
        }
        return distribution, percent, analyzed

    def _sentiment(self, sentiment_counts) -> dict:
        dist, pct, analyzed = self._sentiment_summary(sentiment_counts)
        return {
            "positive": dist["positive"],
            "neutral": dist["neutral"],
            "negative": dist["negative"],
            "positive_percent": pct["positive"],
            "neutral_percent": pct["neutral"],
            "negative_percent": pct["negative"],
            "analyzed_total": analyzed,
        }

    def _platform_breakdown(self, orgs) -> list[dict]:
        """Review-count distribution per platform from operator/scraped org columns."""
        out = []
        for p in _PLATFORM_COLS:
            _, count_col = _PLATFORM_COLS[p]
            total = sum(getattr(o, count_col) or 0 for o in orgs)
            out.append({"platform": p.value, "review_count": total})
        return out

    def _platform_cards(self, orgs, snaps, rating_counts, response_stats) -> list[dict]:
        # Per-platform review-derived metrics (negativity, response speed) computed
        # from period review data, ignoring the platform filter so every card is
        # comparable. Google has no review rows -> those fields stay None.
        cards = []
        for p in _PLATFORM_COLS:
            rated = negative = 0
            for row in rating_counts:
                if row.platform != p or row.rating is None:
                    continue
                rated += row.count
                if row.rating <= 2:
                    negative += row.count
            negativity = round(negative / rated * 100, 1) if rated else None

            stats = response_stats.get(p)
            response_hours = (
                round(stats["sum_seconds"] / 3600 / stats["count"], 1)
                if stats and stats["count"]
                else None
            )
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

    def _attention(self, orgs, platform, snaps, now, aspect_rows, scope) -> list[dict]:
        rules = (
            self.db.query(AttentionRule)
            .filter(AttentionRule.is_enabled.is_(True))
            .order_by(AttentionRule.created_at, AttentionRule.id)
            .all()
        )
        items: list[dict] = []
        for rule in rules:
            scope_ids = self._rule_scope_ids(rule, orgs)
            if not scope_ids:
                continue  # скоуп не пересекается с фильтрами страницы
            rule_orgs = [o for o in orgs if o.id in scope_ids]
            # A rule covering the whole page selection inherits the page's scope,
            # so an unfiltered page keeps issuing IN-clause-free counts.
            rule_scope = scope if len(scope_ids) == len(orgs) else list(scope_ids)
            items.extend(
                self._evaluate_rule(
                    rule, rule_orgs, scope_ids, rule_scope, platform, snaps, now, aspect_rows
                )
            )
        # Внутри severity — по модулю value: у rating_drop value отрицательный,
        # худшее падение должно стоять первым, как и самый большой счётчик.
        items.sort(key=lambda i: (self._SEVERITY_ORDER.get(i["severity"], 9), -abs(i["value"])))
        return items

    @staticmethod
    def _rule_scope_ids(rule: AttentionRule, orgs) -> set[UUID]:
        if rule.scope_type == AttentionScope.company:
            if rule.company_id is None:
                return set()
            return {o.id for o in orgs if o.company_id == rule.company_id}
        selected = {o.id for o in orgs}
        if rule.scope_type == AttentionScope.organizations:
            wanted: set[UUID] = set()
            for raw in rule.organization_ids or []:
                try:
                    wanted.add(UUID(str(raw)))
                except ValueError:
                    continue  # мусорный id (организация удалена) — игнорируем
            return selected & wanted
        return selected

    def _evaluate_rule(
        self, rule, rule_orgs, scope_ids, rule_scope, platform, snaps, now, aspect_rows
    ) -> list[dict]:
        params = rule.params or {}
        scope_list = rule_scope
        if rule.rule_type == AttentionRuleType.unanswered_overdue:
            hours = int(params.get("hours", 24))
            overdue = self._scoped_count(
                scope_list,
                platform,
                Review.response_text.is_(None),
                Review.first_seen_at <= self._dt_param(now - timedelta(hours=hours)),
            )
            found = self._eval_unanswered(overdue, hours=hours)
        elif rule.rule_type == AttentionRuleType.fresh_negative:
            window_hours = int(params.get("window_hours", 2))
            max_rating = int(params.get("max_rating", 2))
            fresh = self._scoped_count(
                scope_list,
                platform,
                Review.rating <= max_rating,
                Review.first_seen_at >= self._dt_param(now - timedelta(hours=window_hours)),
            )
            found = self._eval_fresh_negative(fresh, window_hours=window_hours, max_rating=max_rating)
        elif rule.rule_type == AttentionRuleType.escalated:
            escalated = self._scoped_count(scope_list, platform, Review.status == ReviewStatus.escalated)
            found = self._eval_escalated(escalated)
        elif rule.rule_type == AttentionRuleType.rating_drop:
            found = self._rating_drops(
                rule_orgs, platform, snaps,
                threshold=float(params.get("threshold", -0.2)),
                top=int(params.get("top", 3)),
            )
        else:  # aspect_spike
            found = self._aspect_spikes(
                [r for r in aspect_rows if r.organization_id in scope_ids], now,
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
    def _eval_unanswered(overdue: int, *, hours: int) -> list[dict]:
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
    def _eval_fresh_negative(fresh: int, *, window_hours: int, max_rating: int) -> list[dict]:
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
    def _eval_escalated(escalated: int) -> list[dict]:
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

    def _aspect_spikes(self, aspect_rows, now, *, min_recent: int = 3, top: int = 3) -> list[dict]:
        recent_start = (now - timedelta(days=7)).date()
        prev_start = (now - timedelta(days=14)).date()
        recent: dict[str, int] = {}
        prev: dict[str, int] = {}
        for r in aspect_rows:
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
    def _worst_locations(self, orgs, platform, snaps, unanswered_by_org, *, top: int = 10) -> list[dict]:
        p = ReviewPlatform(platform) if platform != "all" else ReviewPlatform.yandex
        rating_col, _ = _PLATFORM_COLS[p]

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

    def _trending_aspects(self, aspect_rows, now, *, top: int = 8) -> list[dict]:
        recent_start = (now - timedelta(days=7)).date()
        prev_start = (now - timedelta(days=14)).date()
        recent: dict[str, int] = {}
        prev: dict[str, int] = {}
        sentiment: dict[str, dict[str, int]] = {}
        for r in aspect_rows:
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
        # Category breaks mention-count ties: without it the order would follow
        # whatever sequence the rows arrived in, which the database does not promise.
        aspects.sort(key=lambda a: (-a["mentions"], a["category"]))
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
    def _span_days(earliest: datetime | None, now: datetime) -> int:
        if earliest is None:
            return 1
        return max(1, (now - _aware(earliest)).days)

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
