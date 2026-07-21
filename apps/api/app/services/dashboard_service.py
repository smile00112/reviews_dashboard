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

from sqlalchemy import Date, Float, Integer, and_, case, cast, func, literal
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attention_rule import AttentionRule
from app.models.enums import AttentionRuleType, AttentionScope, ReviewPlatform, ReviewStatus
from app.models.organization import Organization
from app.models.rating_snapshot import RatingSnapshot
from app.models.review import Review
from app.services.settings_service import SettingsService

# period token -> window length in days (None = all time / caller-supplied range)
PERIOD_DAYS: dict[str, int | None] = {
    "day": 1,
    "week": 7,
    "30d": 30,
    "90d": 90,
    "year": 365,
    "all": None,
    # feature 013: bounds come from date_from/date_to, not from a fixed length
    "custom": None,
}

CUSTOM_PERIOD = "custom"

# platform -> (org rating column, org review_count column)
_PLATFORM_COLS: dict[ReviewPlatform, tuple[str, str]] = {
    ReviewPlatform.yandex: ("rating", "review_count"),
    ReviewPlatform.gis2: ("gis2_rating", "gis2_review_count"),
    ReviewPlatform.google: ("google_rating", "google_review_count"),
}

# Ratings page (feature 014) presentation constants. Colours match the prototype
# so the hand-rolled SVG charts stay recognisable against the design.
_PLATFORM_LABELS: dict[ReviewPlatform, str] = {
    ReviewPlatform.yandex: "Яндекс Бизнес",
    ReviewPlatform.google: "Google Business",
    ReviewPlatform.gis2: "2ГИС",
}
_PLATFORM_SHORT: dict[ReviewPlatform, str] = {
    ReviewPlatform.yandex: "Яндекс",
    ReviewPlatform.google: "Google",
    ReviewPlatform.gis2: "2ГИС",
}
_PLATFORM_COLORS: dict[ReviewPlatform, str] = {
    ReviewPlatform.yandex: "#ffcc00",
    ReviewPlatform.google: "#4285f4",
    ReviewPlatform.gis2: "#2ecc71",
}
# Platforms we actually collect individual reviews for (Yandex scrapers +
# the 2GIS reviews API, constitution Principle VIII). Google has no collector
# and contributes an aggregate rating/count only, so its per-star, removed and
# response figures are None ("нет данных") rather than a misleading 0.
_PER_REVIEW_PLATFORMS: frozenset[ReviewPlatform] = frozenset(
    {ReviewPlatform.yandex, ReviewPlatform.gis2}
)

_WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_WEEKDAY_FULL = [
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
]


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
        """Baseline snapshot rating per (org, platform) for the period.

        Preferred baseline is the *latest* snapshot taken on or before
        ``period_start`` — the rating as it stood when the period opened. Only
        when no such snapshot exists (snapshot history younger than the period)
        does it fall back to the earliest in-period snapshot, so a short period
        on a fresh install still shows something instead of an em dash.

        Two window-function queries, both O(1) in org count.
        """
        if not org_ids:
            return {}
        before = self._ranked_snapshot_ratings(
            org_ids, RatingSnapshot.captured_on <= period_start, descending=True
        )
        after = self._ranked_snapshot_ratings(
            org_ids, RatingSnapshot.captured_on > period_start, descending=False
        )
        return {**after, **before}

    def _ranked_snapshot_ratings(
        self, org_ids: list[UUID], window_filter, *, descending: bool
    ) -> dict[tuple[UUID, ReviewPlatform], float]:
        """First snapshot rating per (org, platform) inside ``window_filter``, in
        ONE query (window function; supported by PG16 and SQLite >= 3.25)."""
        order = RatingSnapshot.captured_on.desc() if descending else RatingSnapshot.captured_on.asc()
        rn = (
            func.row_number()
            .over(
                partition_by=(RatingSnapshot.organization_id, RatingSnapshot.platform),
                order_by=order,
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
                window_filter,
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

    def _published_expr(self):
        """Publication date of a review: ``review_date`` when the platform gave
        one, else the day we first saw it.

        Period membership ("новых за период", "сегодня") must key off *when the
        review was written*, not when the scraper first saw it: a first bulk
        import of a platform stamps every row with today's ``first_seen_at`` and
        would report the whole backlog as new (2GIS: 35 892 rows -> 34 533 "new
        in day"). ``first_seen_at`` stays the basis for reaction windows
        (2h/24h) and response-delay math, where "since we could have answered"
        is the right clock.
        """
        if self.db.get_bind().dialect.name == "sqlite":
            fallback = func.date(Review.first_seen_at)
        else:
            fallback = cast(Review.first_seen_at, Date)
        return func.coalesce(Review.review_date, fallback)

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
    def _review_cube(
        self,
        org_ids: list[UUID] | None,
        cutoff: datetime | None,
        now: datetime,
        until: date | None = None,
        prev_window: tuple[date, date] | None = None,
        sla_minutes: int | None = None,
    ) -> list:
        """One scan of the scoped reviews, grouped by (platform, rating, sentiment).

        Every counter, distribution and response-delay figure the overview needs is
        folded out of this single result: period membership and the 24h/2h/today
        windows are conditional aggregates rather than separate scans. Always
        platform-agnostic (platform cards need every platform); consumers narrow to
        the page platform in Python.
        """
        delay = self._response_delay_expr()
        answered = Review.response_first_seen_at.isnot(None)
        if sla_minutes is None:
            sla_minutes = settings.overview_sla_threshold_minutes
        sla_seconds = sla_minutes * 60
        fs = Review.first_seen_at
        published = self._published_expr()
        unanswered = Review.response_text.is_(None)
        # Period, "today" and the unanswered card are publication-date based: a
        # bulk import stamps first_seen_at with today for the whole backlog, which
        # would report every old unanswered review as answered-in-time and every
        # backlog row as new. The 2h fresh-negative alert has no day-granular
        # equivalent and stays sighting-based.
        # ``until`` (feature 013) is the optional upper bound of a custom range;
        # None keeps the historical "everything up to now" behaviour.
        period_conds = []
        if cutoff is not None:
            period_conds.append(published >= cutoff.date())
        if until is not None:
            period_conds.append(published <= until)
        in_period = and_(*period_conds) if period_conds else True
        cutoff_2h = self._dt_param(now - timedelta(hours=2))
        # "Today" is an equality, not ``>= today``: platforms hand out timezone-
        # shifted future review_date values (2GIS stamps tomorrow near midnight),
        # which would otherwise be counted as today's.
        today = now.date()
        yesterday = today - timedelta(days=1)

        def cnt(*conds):
            return func.count(case((and_(*conds), 1)))

        # Feature 014: the equally long window right before the period, so the
        # hero cards can show "vs прошлый период" instead of a fixed 24h delta.
        # Absent for period=all (no cutoff -> no previous window to compare to).
        if prev_window is None:
            prev_count = literal(0)
            prev_unanswered = literal(0)
            prev_response_count = literal(0)
            prev_response_sum_seconds = literal(0)
            prev_within_sla = literal(0)
        else:
            in_prev = and_(published >= prev_window[0], published <= prev_window[1])
            prev_count = cnt(in_prev)
            prev_unanswered = cnt(in_prev, unanswered)
            # Feature 014: prev-window response figures for the KPI-strip deltas.
            # prev sentiment / rating shares fall out of prev_count (the cube is
            # grouped by sentiment & rating), so only response stats need columns.
            prev_response_count = cnt(in_prev, answered)
            prev_response_sum_seconds = func.sum(case((and_(in_prev, answered), delay)))
            prev_within_sla = cnt(in_prev, answered, delay <= sla_seconds)

        query = self.db.query(
            Review.platform,
            Review.rating,
            Review.sentiment,
            func.count().label("total"),
            (func.count() if not period_conds else cnt(in_period)).label("count"),
            cnt(published == today).label("new_today"),
            cnt(Review.rating <= 2, fs >= cutoff_2h).label("fresh_negatives_2h"),
            cnt(in_period, unanswered).label("unanswered_total"),
            cnt(in_period, unanswered, published <= yesterday).label("overdue_24h"),
            cnt(in_period, unanswered, published == today).label("unanswered_delta_24h"),
            prev_count.label("prev_count"),
            prev_unanswered.label("prev_unanswered"),
            prev_response_count.label("prev_response_count"),
            prev_response_sum_seconds.label("prev_response_sum_seconds"),
            prev_within_sla.label("prev_within_sla"),
            func.min(published).label("min_published"),
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
            "prev_count",
            "prev_unanswered",
        )
        totals = {k: 0 for k in keys}
        earliest = None
        for row in cube:
            if page_platforms is not None and row.platform not in page_platforms:
                continue
            for k in keys:
                totals[k] += getattr(row, k)
            if row.min_published is not None and (earliest is None or row.min_published < earliest):
                earliest = row.min_published
        totals["new_in_period"] = totals.pop("count")
        totals["min_published"] = earliest
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
            entry = stats.setdefault(
                row.platform,
                {
                    "count": 0, "sum_seconds": 0.0, "within_sla": 0,
                    "prev_count": 0, "prev_sum_seconds": 0.0, "prev_within_sla": 0,
                },
            )
            entry["count"] += row.response_count
            entry["sum_seconds"] += float(row.response_sum_seconds or 0.0)
            entry["within_sla"] += row.within_sla
            entry["prev_count"] += row.prev_response_count
            entry["prev_sum_seconds"] += float(row.prev_response_sum_seconds or 0.0)
            entry["prev_within_sla"] += row.prev_within_sla
        return stats

    def _unanswered_by_org(
        self,
        org_ids: list[UUID] | None,
        platform: str,
        cutoff: datetime | None,
        until: date | None = None,
    ) -> dict[UUID, int]:
        """Per-org unanswered count, scoped to the page period by publication date
        (same clock as the "Без ответа" hero card)."""
        filters = [*self._scoped_filters(org_ids, platform), Review.response_text.is_(None)]
        if cutoff is not None:
            filters.append(self._published_expr() >= cutoff.date())
        if until is not None:
            filters.append(self._published_expr() <= until)
        query = self.db.query(Review.organization_id, func.count()).filter(*filters)
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

    def _response_base(
        self, org_ids: list[UUID] | None, cutoff: datetime | None, until: date | None = None
    ):
        """Filtered query base over period rows carrying a response (platform-agnostic)."""
        filters = [Review.response_first_seen_at.isnot(None)]
        if org_ids is not None:
            filters.append(Review.organization_id.in_(org_ids))
        if cutoff is not None:
            filters.append(self._published_expr() >= cutoff.date())
        if until is not None:
            filters.append(self._published_expr() <= until)
        return filters

    def _response_percentiles(
        self,
        org_ids: list[UUID] | None,
        cutoff: datetime | None,
        platform: str,
        until: date | None = None,
    ) -> tuple[float | None, float | None]:
        """(median, p95) response delay in seconds for the page's platform scope.

        PostgreSQL computes them with ``percentile_cont`` (linear interpolation —
        the same definition as ``statistics.median`` and ``_percentile``); SQLite,
        which lacks it, falls back to loading the delays.
        """
        delay = self._response_delay_expr()
        filters = list(self._response_base(org_ids, cutoff, until))
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
        date_from: date | None = None,
        date_to: date | None = None,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc)
        days = PERIOD_DAYS.get(period, 30)
        until: date | None = None
        if period == CUSTOM_PERIOD and date_from is not None and date_to is not None:
            # Feature 013: caller-supplied window, both bounds inclusive. ``days``
            # counts calendar days in the range so avg_per_day stays honest.
            cutoff = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
            until = date_to
            days = (date_to - date_from).days + 1
        else:
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

        sla_minutes = SettingsService(self.db).sla_threshold_minutes()

        # Previous window of the same length, ending the day before the period
        # starts. period=all has no cutoff, so no comparison base.
        prev_window = None
        if cutoff is not None and days:
            prev_end = period_start - timedelta(days=1)
            prev_window = (prev_end - timedelta(days=days - 1), prev_end)

        cube = self._review_cube(scope, cutoff, now, until, prev_window, sla_minutes)
        counters = self._counters_from_cube(cube, page_platforms)
        rating_counts = cube
        sentiment_counts = self._sentiment_counts_from_cube(cube, page_platforms)
        response_stats = self._response_stats_from_cube(cube)
        unanswered_by_org = self._unanswered_by_org(scope, platform, cutoff, until)
        response_percentiles = self._response_percentiles(scope, cutoff, platform, until)
        aspect_rows = self._aspect_rows(scope, platform, now)

        header = self._header(counters)
        kpi_hero = self._kpi_hero(
            orgs, counters, platform, snaps, days, now, has_prev=prev_window is not None
        )
        kpi_strip = self._kpi_strip(
            response_stats, response_percentiles, rating_counts, sentiment_counts, page_platforms,
            has_prev=prev_window is not None,
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

    def _kpi_hero(self, orgs, counters, platform, snaps, days, now, *, has_prev=False) -> dict:
        # Weighted network average rating over the platform's org columns.
        avg_rating = self._weighted_avg_rating(orgs, platform)
        delta = self._network_rating_delta(orgs, platform, snaps)

        span = days or max(1, self._span_days(counters["min_published"], now))
        new_in_period = counters["new_in_period"]
        return {
            "network_avg_rating": avg_rating,
            "network_avg_rating_delta": delta,
            "new_in_period": new_in_period,
            "new_today": counters["new_today"],
            # Feature 014: period-over-period deltas. None when the period has no
            # comparable predecessor (period=all).
            "new_in_period_delta": (new_in_period - counters["prev_count"]) if has_prev else None,
            "unanswered_delta_period": (
                (counters["unanswered_total"] - counters["prev_unanswered"]) if has_prev else None
            ),
            "period_days": days,
            "total_reviews": counters["total"],
            "avg_per_day": round(new_in_period / span, 1) if span else 0.0,
            "unanswered_total": counters["unanswered_total"],
            "unanswered_delta_24h": counters["unanswered_delta_24h"],
            "overdue_24h": counters["overdue_24h"],
        }

    def _kpi_strip(
        self, response_stats, percentiles, rating_counts, sentiment_counts, page_platforms,
        *, has_prev: bool = False,
    ) -> dict:
        # Current + previous-window response totals in one pass (feature 014).
        count = sum_seconds = within_sla = 0
        prev_count_r = prev_sum = prev_within_sla = 0
        for p, stats in response_stats.items():
            if page_platforms is not None and p not in page_platforms:
                continue
            count += stats["count"]
            sum_seconds += stats["sum_seconds"]
            within_sla += stats["within_sla"]
            prev_count_r += stats["prev_count"]
            prev_sum += stats["prev_sum_seconds"]
            prev_within_sla += stats["prev_within_sla"]
        sla_percent = round(within_sla / count * 100, 1) if count else None
        median_seconds, p95_seconds = percentiles

        # Current + previous rating shares (for reputation index) in one pass.
        n = share5_count = share13_count = 0
        pn = pshare5 = pshare13 = 0
        prev_sentiment_counts: dict = {}
        for row in rating_counts:
            if page_platforms is not None and row.platform not in page_platforms:
                continue
            prev_sentiment_counts[row.sentiment] = (
                prev_sentiment_counts.get(row.sentiment, 0) + row.prev_count
            )
            if row.rating is None:
                continue
            n += row.count
            pn += row.prev_count
            if row.rating == 5:
                share5_count += row.count
                pshare5 += row.prev_count
            if row.rating <= 3:
                share13_count += row.count
                pshare13 += row.prev_count
        reputation = round(share5_count / n * 100 - share13_count / n * 100, 1) if n else None

        _, sentiment_percent, _ = self._sentiment_summary(sentiment_counts)

        response_avg_min = round(sum_seconds / count / 60) if count else None

        # Deltas: current minus the equally long prior window. None when the period
        # has no predecessor (period=all) or the prior window has no matching rows
        # to compare against — a bare "+22 мин" off an empty base would mislead.
        prev_avg_min = round(prev_sum / prev_count_r / 60) if prev_count_r else None
        prev_sla = round(prev_within_sla / prev_count_r * 100, 1) if prev_count_r else None
        prev_reputation = (
            round(pshare5 / pn * 100 - pshare13 / pn * 100, 1) if pn else None
        )
        _, prev_sentiment_percent, prev_analyzed = self._sentiment_summary(prev_sentiment_counts)

        return {
            "response_avg_min": response_avg_min,
            "response_median_min": round(median_seconds / 60) if median_seconds is not None else None,
            "response_p95_min": round(p95_seconds / 60) if p95_seconds is not None else None,
            "response_approximate": True,
            "sla_percent": sla_percent,
            "positivity_percent": sentiment_percent["positive"],
            "reputation_index": reputation,
            # Lower response time is better; the frontend colours it accordingly.
            "response_avg_min_delta": (
                response_avg_min - prev_avg_min
                if has_prev and response_avg_min is not None and prev_avg_min is not None
                else None
            ),
            "sla_percent_delta": (
                round(sla_percent - prev_sla, 1)
                if has_prev and sla_percent is not None and prev_sla is not None
                else None
            ),
            "positivity_percent_delta": (
                round(sentiment_percent["positive"] - prev_sentiment_percent["positive"], 1)
                if has_prev and prev_analyzed
                else None
            ),
            "reputation_index_delta": (
                round(reputation - prev_reputation, 1)
                if has_prev and reputation is not None and prev_reputation is not None
                else None
            ),
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
    def _span_days(earliest: date | datetime | str | None, now: datetime) -> int:
        """Days covered by the data. ``earliest`` is a publication date; SQLite
        hands back the ISO string its coalesce produced, Postgres a ``date``."""
        if earliest is None:
            return 1
        if isinstance(earliest, str):
            earliest = date.fromisoformat(earliest[:10])
        if isinstance(earliest, datetime):
            return max(1, (now - _aware(earliest)).days)
        return max(1, (now.date() - earliest).days)

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
                "new_in_period_delta": None,
                "unanswered_delta_period": None,
                "period_days": PERIOD_DAYS.get(period, 30),
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
                "response_avg_min_delta": None,
                "sla_percent_delta": None,
                "positivity_percent_delta": None,
                "reputation_index_delta": None,
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

    # ------------------------------------------------------------------ #
    # Ratings page (feature 014)                                          #
    #                                                                     #
    # Comparative rating analytics: per-platform star distribution,       #
    # monthly rating/volume trends from rating_snapshot, weekly response  #
    # percentiles, and a weekday breakdown. Read-only; every figure is a  #
    # deterministic SQL aggregate (constitution Principle VI).            #
    # ------------------------------------------------------------------ #
    def _month_key_expr(self, column):
        """``YYYY-MM`` bucket key for a date column, per dialect."""
        if self.db.get_bind().dialect.name == "sqlite":
            return func.strftime("%Y-%m", column)
        return func.to_char(column, "YYYY-MM")

    def _week_key_expr(self, column):
        """``YYYY-Www`` ISO-week bucket key for a date column, per dialect."""
        if self.db.get_bind().dialect.name == "sqlite":
            # %W = week of year, Monday as first day — matches ISO closely enough
            # for bucketing/labelling (tests only run on SQLite).
            return func.strftime("%Y-W%W", column)
        return func.to_char(column, 'IYYY"-W"IW')

    def _weekday_expr(self, column):
        """Weekday index normalized to 0 = Monday .. 6 = Sunday, per dialect."""
        if self.db.get_bind().dialect.name == "sqlite":
            # strftime('%w') is 0=Sunday..6=Saturday -> shift to Monday-first.
            return (cast(func.strftime("%w", column), Integer) + 6) % 7
        # isodow is 1=Monday..7=Sunday -> shift to 0-based.
        return cast(func.extract("isodow", column), Integer) - 1

    def ratings(
        self,
        *,
        period: str = "30d",
        platform: str = "all",
        org_ids: list[UUID] | None = None,
        company_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        now: datetime | None = None,
    ) -> dict:
        """Composed payload for the ratings page.

        Period/platform/scope semantics are identical to ``overview`` — the page
        reuses the same filter component, so any divergence would be a bug.
        """
        now = now or datetime.now(timezone.utc)
        days = PERIOD_DAYS.get(period, 30)
        until: date | None = None
        if period == CUSTOM_PERIOD and date_from is not None and date_to is not None:
            cutoff = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
            until = date_to
            days = (date_to - date_from).days + 1
        else:
            cutoff = None if days is None else now - timedelta(days=days)

        orgs = self._selected_orgs(org_ids, company_id)
        selected_ids = [o.id for o in orgs]

        sla_minutes = SettingsService(self.db).sla_threshold_minutes()
        empty = self._empty_ratings_payload(period, platform, now, sla_minutes)
        if not selected_ids:
            return empty

        # Whole network selected -> drop the IN clause entirely (feature 012).
        scope = None if (not org_ids and company_id is None) else selected_ids
        page_platforms = (
            list(_PLATFORM_COLS.keys()) if platform == "all" else [ReviewPlatform(platform)]
        )

        return {
            **empty,
            "platform_distribution": self._platform_distribution(
                orgs, scope, page_platforms, cutoff, until
            ),
            **self._snapshot_trends(selected_ids, page_platforms, cutoff, until),
            "response_speed": self._response_speed_weekly(
                scope, platform, cutoff, until, sla_minutes
            ),
            "weekday": self._weekday_stats(scope, platform, cutoff, until),
        }

    def _empty_ratings_payload(
        self, period: str, platform: str, now: datetime, sla_minutes: int
    ) -> dict:
        return {
            "period": period,
            "platform": platform,
            "generated_at": now,
            "platform_distribution": [],
            "rating_trend": {"labels": [], "series": []},
            "volume_trend": {"labels": [], "series": []},
            "response_speed": {
                "labels": [],
                "median_minutes": [],
                "p95_minutes": [],
                "sla_target_minutes": sla_minutes,
            },
            "weekday": {"days": self._empty_weekdays(), "insight": None},
        }

    @staticmethod
    def _empty_weekdays() -> list[dict]:
        return [
            {"weekday": i, "label": label, "count": 0, "avg_rating": None}
            for i, label in enumerate(_WEEKDAY_LABELS)
        ]

    def _star_scan(
        self,
        org_ids: list[UUID] | None,
        cutoff: datetime | None,
        until: date | None,
    ) -> list:
        """One grouped scan of scoped reviews by (platform, rating).

        Active and removed rows are separated by conditional counts rather than
        two queries, so the statement count stays constant (feature 012).
        """
        filters = list(self._scoped_filters(org_ids, "all"))
        published = self._published_expr()
        if cutoff is not None:
            filters.append(published >= cutoff.date())
        if until is not None:
            filters.append(published <= until)
        return (
            self.db.query(
                Review.platform,
                Review.rating,
                func.count(case((Review.removed_at.is_(None), 1))).label("active_count"),
                func.count(case((Review.removed_at.isnot(None), 1))).label("removed_count"),
            )
            .filter(*filters)
            .group_by(Review.platform, Review.rating)
            .all()
        )

    def _platform_distribution(
        self,
        orgs,
        org_ids: list[UUID] | None,
        page_platforms: list[ReviewPlatform],
        cutoff: datetime | None,
        until: date | None,
    ) -> list[dict]:
        """Per-platform average rating + 5★..1★ shares + removed count.

        For platforms that store individual reviews (Yandex) every figure comes
        from the scoped review rows, so the average and the star breakdown are
        internally consistent and both honour the period. Aggregate-only
        platforms (Google, 2ГИС) fall back to the organization's stored rating
        and count, and report ``None`` — not 0 — for the per-review columns.
        """
        scan = self._star_scan(org_ids, cutoff, until)
        active: dict[tuple[ReviewPlatform, int], int] = {}
        removed: dict[ReviewPlatform, int] = {}
        for row in scan:
            active[(row.platform, row.rating)] = (
                active.get((row.platform, row.rating), 0) + row.active_count
            )
            removed[row.platform] = removed.get(row.platform, 0) + row.removed_count

        rows: list[dict] = []
        for p in page_platforms:
            if p in _PER_REVIEW_PLATFORMS:
                counts = {star: active.get((p, star), 0) for star in range(1, 6)}
                total = sum(counts.values())
                stars = [
                    {
                        "star": star,
                        "count": counts[star],
                        "share": round(counts[star] / total * 100, 1) if total else 0.0,
                    }
                    # 5★ first, matching the prototype's column order
                    for star in range(5, 0, -1)
                ]
                weighted = sum(star * n for star, n in counts.items())
                rows.append({
                    "platform": p.value,
                    "label": _PLATFORM_LABELS[p],
                    "avg_rating": round(weighted / total, 2) if total else None,
                    "total_reviews": total,
                    "stars": stars,
                    "removed_count": removed.get(p, 0),
                })
                continue

            rating_col, count_col = _PLATFORM_COLS[p]
            num = 0.0
            den = 0
            for org in orgs:
                rating = getattr(org, rating_col)
                count = getattr(org, count_col) or 0
                if rating is not None and count:
                    num += float(rating) * count
                    den += count
            rows.append({
                "platform": p.value,
                "label": _PLATFORM_LABELS[p],
                "avg_rating": round(num / den, 2) if den else None,
                "total_reviews": den or None,
                # No per-review rows for this platform -> «нет данных», not 0.
                "stars": None,
                "removed_count": None,
            })
        return rows

    def _snapshot_trends(
        self,
        org_ids: list[UUID],
        page_platforms: list[ReviewPlatform],
        cutoff: datetime | None,
        until: date | None,
    ) -> dict:
        """Monthly average-rating and review-volume series per platform.

        Sourced from ``rating_snapshot``, not from live review counts: a bulk
        import stamps the whole backlog with one ``first_seen_at``, which would
        distort a review-derived volume trend (the same reason
        ``_published_expr`` exists). Within a month the **latest** snapshot per
        (organization, platform) is the month's reading; those are then
        aggregated across the selected organizations — volume summed, rating
        weighted by review_count. Months with no snapshot for a platform stay
        ``None`` (a gap in the line), never 0.
        """
        month = self._month_key_expr(RatingSnapshot.captured_on)
        filters = [
            RatingSnapshot.organization_id.in_(org_ids),
            RatingSnapshot.platform.in_(page_platforms),
        ]
        if cutoff is not None:
            filters.append(RatingSnapshot.captured_on >= cutoff.date())
        if until is not None:
            filters.append(RatingSnapshot.captured_on <= until)

        # Latest capture day per (org, platform, month) ...
        latest = (
            self.db.query(
                RatingSnapshot.organization_id.label("org_id"),
                RatingSnapshot.platform.label("platform"),
                month.label("month"),
                func.max(RatingSnapshot.captured_on).label("last_day"),
            )
            .filter(*filters)
            .group_by(RatingSnapshot.organization_id, RatingSnapshot.platform, month)
            .subquery()
        )
        # ... folded to one row per (month, platform) so the result set stays
        # bounded by months x platforms regardless of organization count.
        weight = func.coalesce(RatingSnapshot.review_count, 1)
        rated = RatingSnapshot.rating.isnot(None)
        rows = (
            self.db.query(
                latest.c.month.label("month"),
                RatingSnapshot.platform.label("platform"),
                func.sum(case((rated, RatingSnapshot.rating * weight))).label("rating_num"),
                func.sum(case((rated, weight))).label("rating_den"),
                func.sum(func.coalesce(RatingSnapshot.review_count, 0)).label("volume"),
            )
            .join(
                latest,
                and_(
                    RatingSnapshot.organization_id == latest.c.org_id,
                    RatingSnapshot.platform == latest.c.platform,
                    RatingSnapshot.captured_on == latest.c.last_day,
                ),
            )
            .group_by(latest.c.month, RatingSnapshot.platform)
            .all()
        )

        ratings: dict[tuple[str, ReviewPlatform], float] = {}
        volumes: dict[tuple[str, ReviewPlatform], int] = {}
        months: set[str] = set()
        for row in rows:
            months.add(row.month)
            den = float(row.rating_den or 0)
            if den:
                ratings[(row.month, row.platform)] = round(float(row.rating_num) / den, 2)
            volumes[(row.month, row.platform)] = int(row.volume or 0)

        labels = sorted(months)
        if not labels:
            return {
                "rating_trend": {"labels": [], "series": []},
                "volume_trend": {"labels": [], "series": []},
            }

        # Only platforms that actually have history get a series — an all-None
        # line would render as an empty legend entry.
        def build(source: dict) -> list[dict]:
            series = []
            for p in page_platforms:
                points = [source.get((m, p)) for m in labels]
                if all(pt is None for pt in points):
                    continue
                series.append({
                    "platform": p.value,
                    "label": _PLATFORM_SHORT[p],
                    "color": _PLATFORM_COLORS[p],
                    "points": points,
                })
            return series

        return {
            "rating_trend": {"labels": labels, "series": build(ratings)},
            "volume_trend": {"labels": labels, "series": build(volumes)},
        }

    def _response_speed_weekly(
        self,
        org_ids: list[UUID] | None,
        platform: str,
        cutoff: datetime | None,
        until: date | None,
        sla_minutes: int,
    ) -> dict:
        """Weekly median / p95 response delay, in minutes.

        Extends ``_response_percentiles`` from one figure to a weekly series.
        Median and p95 (not the mean) because the response distribution has a
        long tail — a handful of very late replies would make an average look
        far worse than the typical experience.
        """
        delay = self._response_delay_expr()
        week = self._week_key_expr(self._published_expr())
        filters = list(self._response_base(org_ids, cutoff, until))
        if platform != "all":
            filters.append(Review.platform == ReviewPlatform(platform))

        buckets: dict[str, tuple[float | None, float | None]] = {}
        if self.db.get_bind().dialect.name == "sqlite":
            # No percentile_cont: pull the delays per week and fold in Python.
            per_week: dict[str, list[float]] = {}
            rows = (
                self.db.query(week.label("week"), delay.label("delay"))
                .select_from(Review)
                .filter(*filters)
                .all()
            )
            for row in rows:
                if row.delay is not None:
                    per_week.setdefault(row.week, []).append(float(row.delay))
            for key, values in per_week.items():
                buckets[key] = (median(values), float(self._percentile(values, 95)))
        else:
            rows = (
                self.db.query(
                    week.label("week"),
                    func.percentile_cont(0.5).within_group(delay.asc()).label("median"),
                    func.percentile_cont(0.95).within_group(delay.asc()).label("p95"),
                )
                .select_from(Review)
                .filter(*filters)
                .group_by(week)
                .all()
            )
            for row in rows:
                if row.median is not None:
                    buckets[row.week] = (float(row.median), float(row.p95))

        labels = sorted(buckets)
        to_min = lambda seconds: round(seconds / 60.0, 1)  # noqa: E731
        return {
            "labels": labels,
            "median_minutes": [to_min(buckets[k][0]) for k in labels],
            "p95_minutes": [to_min(buckets[k][1]) for k in labels],
            "sla_target_minutes": sla_minutes,
        }

    def _weekday_stats(
        self,
        org_ids: list[UUID] | None,
        platform: str,
        cutoff: datetime | None,
        until: date | None,
    ) -> dict:
        """Review count and average rating per weekday (Mon..Sun).

        Keyed on ``review_date`` — the only real posting-time signal we store.
        Reviews without a parsed date are excluded from this block (they still
        count everywhere else); there is deliberately no hour-of-day axis,
        because posting time is not recorded (``first_seen_at`` is scrape time).
        """
        filters = [
            *self._scoped_filters(org_ids, platform),
            Review.removed_at.is_(None),
            Review.review_date.isnot(None),
        ]
        published = self._published_expr()
        if cutoff is not None:
            filters.append(published >= cutoff.date())
        if until is not None:
            filters.append(published <= until)

        weekday = self._weekday_expr(Review.review_date)
        rows = (
            self.db.query(
                weekday.label("weekday"),
                func.count().label("count"),
                func.avg(Review.rating).label("avg_rating"),
            )
            .filter(*filters)
            .group_by(weekday)
            .all()
        )

        days = self._empty_weekdays()
        for row in rows:
            idx = int(row.weekday)
            if 0 <= idx <= 6:
                days[idx]["count"] = int(row.count)
                days[idx]["avg_rating"] = (
                    round(float(row.avg_rating), 2) if row.avg_rating is not None else None
                )

        result = {"days": days, "insight": self._weekday_insight(days)}

        if cutoff is not None and until is not None:
            result["grid"] = self._weekday_grid(filters, cutoff, until)
        return result

    def _bucket_key_for_date(self, gran: str, d: date) -> str:
        """Format a bucket key for ``d`` so it matches the SQL group-by key
        produced by ``_weekday_grid_bucket_expr`` for the same granularity,
        on whichever dialect is active."""
        if gran == "day":
            return d.isoformat()
        if gran == "week":
            if self.db.get_bind().dialect.name == "sqlite":
                # Mirrors _week_key_expr's strftime('%Y-W%W', ...) on SQLite.
                # NOTE: %W is calendar week-of-year (weeks start Monday, week 00
                # is the partial week before the first Monday), not ISO week —
                # it can diverge from the isocalendar() branch below at a year
                # boundary, so a weekly custom range spanning Jan 1 could split
                # a week across two columns in SQLite-backed tests only.
                # Production (Postgres, to_char(..., 'IYYY-IW')) is pure ISO
                # and unaffected.
                return d.strftime("%Y-W%W")
            iso_year, iso_week, _ = d.isocalendar()
            return f"{iso_year:04d}-W{iso_week:02d}"
        return f"{d.year:04d}-{d.month:02d}"

    @staticmethod
    def _weekday_grid_granularity(start: date, end: date) -> str:
        span_days = (end - start).days + 1  # inclusive
        if span_days <= 14:
            return "day"
        if span_days <= 92:
            return "week"
        return "month"

    _RU_MONTHS_SHORT = [
        "янв", "фев", "мар", "апр", "май", "июн",
        "июл", "авг", "сен", "окт", "ноя", "дек",
    ]

    def _weekday_grid_columns(self, gran: str, start: date, end: date) -> list[dict]:
        """Ordered ``[{"key", "label"}]`` covering the whole range, including
        empty periods. Keys are derived via ``_bucket_key_for_date`` so they
        are guaranteed to match the SQL group-by keys on both dialects."""
        cols: list[dict] = []
        if gran == "day":
            cur = start
            while cur <= end:
                cols.append({
                    "key": self._bucket_key_for_date(gran, cur),
                    "label": f"{cur.day} {self._RU_MONTHS_SHORT[cur.month - 1]}",
                })
                cur += timedelta(days=1)
        elif gran == "week":
            # Bucket by week; walk week-by-week from the Monday of `start`.
            cur = start - timedelta(days=start.weekday())
            while cur <= end:
                iso_year, iso_week, _ = cur.isocalendar()
                cols.append({
                    "key": self._bucket_key_for_date(gran, cur),
                    "label": f"нед. {iso_week}",
                })
                cur += timedelta(days=7)
        else:  # month
            y, m = start.year, start.month
            cur = date(y, m, 1)
            while (cur.year, cur.month) <= (end.year, end.month):
                cols.append({
                    "key": self._bucket_key_for_date(gran, cur),
                    "label": self._RU_MONTHS_SHORT[cur.month - 1].capitalize(),
                })
                if cur.month == 12:
                    cur = date(cur.year + 1, 1, 1)
                else:
                    cur = date(cur.year, cur.month + 1, 1)
        return cols

    def _weekday_grid_bucket_expr(self, gran: str):
        """SQL expression whose grouped values equal the column ``key``s from
        ``_weekday_grid_columns``/``_bucket_key_for_date``, on both dialects."""
        if gran == "day":
            if self.db.get_bind().dialect.name == "sqlite":
                return func.strftime("%Y-%m-%d", Review.review_date)
            return func.to_char(Review.review_date, "YYYY-MM-DD")
        if gran == "week":
            return self._week_key_expr(Review.review_date)
        return self._month_key_expr(Review.review_date)

    def _weekday_grid(self, scope_filters: list, cutoff: datetime, until: date) -> dict:
        """Weekday x date-period heatmap for a custom range.

        Reuses ``scope_filters`` already assembled by ``_weekday_stats``
        (scope, ``removed_at IS NULL``, ``review_date IS NOT NULL``, and the
        published-range bounds) so this stays a single additional GROUP BY
        scan replacing, not adding to, the bars query's cost profile.
        """
        start, end = cutoff.date(), until
        gran = self._weekday_grid_granularity(start, end)
        columns = self._weekday_grid_columns(gran, start, end)
        col_index = {c["key"]: i for i, c in enumerate(columns)}

        weekday = self._weekday_expr(Review.review_date)
        bucket = self._weekday_grid_bucket_expr(gran)
        rows = (
            self.db.query(
                weekday.label("weekday"),
                bucket.label("bucket"),
                func.count().label("count"),
                func.avg(Review.rating).label("avg_rating"),
            )
            .filter(*scope_filters)
            .group_by(weekday, bucket)
            .all()
        )

        cells = [
            [{"count": 0, "avg_rating": None} for _ in columns]
            for _ in range(7)
        ]
        for r in rows:
            ci = col_index.get(r.bucket)
            wi = int(r.weekday)
            if ci is None or not (0 <= wi <= 6):
                continue
            cells[wi][ci] = {
                "count": int(r.count),
                "avg_rating": round(float(r.avg_rating), 2) if r.avg_rating is not None else None,
            }

        grid_rows = [
            {"weekday": i, "label": _WEEKDAY_LABELS[i], "cells": cells[i]}
            for i in range(7)
        ]
        return {
            "columns": columns,
            "rows": grid_rows,
            "insight": self._weekday_grid_insight(grid_rows, columns),
        }

    @staticmethod
    def _weekday_grid_insight(grid_rows: list[dict], columns: list[dict]) -> str | None:
        """"Worst cell / best cell" sentence naming both the weekday AND the
        period column, since a grid cell is one (weekday, period) pair, not a
        whole weekday's aggregate — attributing it to the weekday alone would
        misrepresent which period the extreme rating came from."""
        rated = [
            (row["label"], columns[i]["label"], c["avg_rating"])
            for row in grid_rows
            for i, c in enumerate(row["cells"])
            if c["avg_rating"] is not None
        ]
        if len(rated) < 2:
            return None
        worst = min(rated, key=lambda t: t[2])
        best = max(rated, key=lambda t: t[2])
        if worst[2] == best[2]:
            return None
        return (
            f"Худшие оценки — {worst[0]}, {worst[1]} (средняя {worst[2]:.2f}). "
            f"Лучшие — {best[0]}, {best[1]} ({best[2]:.2f})."
        )

    @staticmethod
    def _weekday_insight(days: list[dict]) -> str | None:
        """"Worst day / best day" sentence, or None when there is nothing to compare."""
        rated = [d for d in days if d["avg_rating"] is not None]
        if len(rated) < 2:
            return None
        worst = min(rated, key=lambda d: d["avg_rating"])
        best = max(rated, key=lambda d: d["avg_rating"])
        if worst["weekday"] == best["weekday"]:
            return None
        return (
            f"Пик жалоб — {_WEEKDAY_FULL[worst['weekday']]} "
            f"(средняя оценка {worst['avg_rating']:.2f}). "
            f"Лучшие оценки — {_WEEKDAY_FULL[best['weekday']]} "
            f"({best['avg_rating']:.2f})."
        )
