import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.analyzer import ReviewAnalyzer
from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.normalize import build_review_hash
from app.scraper.types import ParsedReview

logger = logging.getLogger(__name__)

# Feed period presets (days back from now). "24h" is 1 day because review
# dates have day precision.
PERIOD_DAYS: dict[str, int] = {"24h": 1, "7d": 7, "30d": 30, "year": 365}


def has_aspect(review: Review, aspect: str) -> bool:
    """True when the review's problems JSONB contains the category.

    Python-side on purpose: the SQLite test backend has no JSONB operators.
    """
    return any(p.get("category") == aspect for p in (review.problems or []))


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware. Normalize to UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ReviewService:
    def __init__(self, db: Session):
        self.db = db
        self._analyzer = ReviewAnalyzer()

    def _apply_analysis(self, review: Review, now: datetime) -> None:
        """Assign derived analytics. Called strictly AFTER the content_hash is built,
        so analysis never influences deduplication."""
        result = self._analyzer.analyze(review.review_text, review.rating)
        review.sentiment = result["sentiment"]
        review.sentiment_score = result["sentiment_score"]
        review.sentiment_confidence = result["sentiment_confidence"]
        review.rating_sentiment_mismatch = result["rating_sentiment_mismatch"]
        review.problems = result["problems"]
        review.analyzed_at = now

    def upsert_reviews(
        self,
        organization_id: UUID,
        reviews: list[ParsedReview],
        scrape_mode: ScrapeMode,
    ) -> tuple[int, int, int]:
        seen = 0
        inserted = 0
        updated = 0
        now = datetime.now(timezone.utc)

        # Provenance derived from the scrape mode. Never a content_hash input.
        is_twogis = scrape_mode == ScrapeMode.twogis_api
        source = "2gis" if is_twogis else "yandex_maps"
        platform = ReviewPlatform.gis2 if is_twogis else ReviewPlatform.yandex

        # Hash first (dedup contract), then batch-preload existing rows in ONE query
        # instead of a SELECT per review.
        hashed: list[tuple[ParsedReview, str]] = []
        for parsed in reviews:
            seen += 1
            hashed.append(
                (
                    parsed,
                    build_review_hash(
                        parsed.author_name,
                        parsed.rating,
                        parsed.review_date_text,
                        parsed.review_text,
                    ),
                )
            )

        existing_by_hash: dict[str, Review] = {}
        if hashed:
            rows = (
                self.db.query(Review)
                .filter(
                    Review.organization_id == organization_id,
                    Review.content_hash.in_({h for _, h in hashed}),
                )
                .all()
            )
            existing_by_hash = {row.content_hash: row for row in rows}

        for parsed, content_hash in hashed:
            existing = existing_by_hash.get(content_hash)
            if existing is not None:
                self._apply_update(existing, parsed, now)
                updated += 1
                continue

            review = Review(
                organization_id=organization_id,
                source=source,
                scrape_mode=scrape_mode,
                platform=platform,
                external_review_id=parsed.external_review_id,
                author_name=parsed.author_name,
                rating=parsed.rating,
                review_text=parsed.review_text,
                review_date_text=parsed.review_date_text,
                review_date=parsed.review_date,
                response_text=parsed.response_text,
                response_first_seen_at=now if parsed.response_text else None,
                content_hash=content_hash,
                first_seen_at=now,
                last_seen_at=now,
            )
            self._apply_analysis(review, now)
            # SAVEPOINT per insert: a concurrent-duplicate IntegrityError rolls back
            # only this row, never the previously flushed inserts of the batch.
            try:
                with self.db.begin_nested():
                    self.db.add(review)
                    self.db.flush()
                inserted += 1
                existing_by_hash[content_hash] = review
            except IntegrityError:
                logger.warning(
                    "review insert collision, retrying as update org=%s hash=%s",
                    organization_id,
                    content_hash[:12],
                )
                collided = (
                    self.db.query(Review)
                    .filter(
                        Review.organization_id == organization_id,
                        Review.content_hash == content_hash,
                    )
                    .first()
                )
                if collided is not None:
                    self._apply_update(collided, parsed, now)
                    updated += 1
                    existing_by_hash[content_hash] = collided

        self.db.commit()
        return seen, inserted, updated

    def _apply_update(self, existing: Review, parsed: ParsedReview, now: datetime) -> None:
        existing.last_seen_at = now
        if parsed.response_text and not existing.response_text:
            # Response first appears on this run: record text + first-observed time (once).
            existing.response_text = parsed.response_text
            existing.response_first_seen_at = now
        elif parsed.response_text:
            # Response already recorded: refresh text (e.g. business edit), keep the timestamp.
            existing.response_text = parsed.response_text
        if existing.analyzed_at is None:
            self._apply_analysis(existing, now)

    def list_for_organization(
        self,
        organization_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        rating: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[Review], int]:
        query = self.db.query(Review).filter(Review.organization_id == organization_id)
        query = self._apply_filters(query, rating, date_from, date_to, new_only=False)
        total = query.count()
        items = (
            query.order_by(desc(Review.review_date).nullslast(), desc(Review.first_seen_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    def list_global(
        self,
        *,
        organization_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        rating: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        new_only: bool = False,
        status_tab: str | None = None,
        platform: ReviewPlatform | None = None,
        tone: str | None = None,
        period: str | None = None,
        is_paid: bool | None = None,
        aspect: str | None = None,
        sort: str = "new",
    ) -> tuple[list[tuple[Review, str | None]], int]:
        query = self.db.query(Review, Organization.name).join(Organization)
        if organization_id:
            query = query.filter(Review.organization_id == organization_id)
        query = self._apply_filters(query, rating, date_from, date_to, new_only=new_only)
        query = self._apply_feed_filters(
            query, status_tab=status_tab, platform=platform, tone=tone, period=period, is_paid=is_paid
        )
        ordered = self._apply_sort(query, sort)
        if aspect:
            # Python-side aspect match (no JSONB operators on SQLite): fetch the
            # filtered feed, then filter + paginate in memory. Volumes are the
            # same order as the dashboard aggregates, which already do this.
            rows = [row for row in ordered.all() if has_aspect(row[0], aspect)]
            return rows[offset : offset + limit], len(rows)
        total = query.count()
        rows = ordered.offset(offset).limit(limit).all()
        return rows, total

    def _apply_filters(self, query, rating, date_from, date_to, new_only: bool):
        if rating is not None:
            query = query.filter(Review.rating == rating)
        if date_from is not None:
            query = query.filter(Review.review_date >= date_from)
        if date_to is not None:
            query = query.filter(Review.review_date <= date_to)
        if new_only:
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            query = query.filter(Review.first_seen_at >= cutoff)
        return query

    def _apply_feed_filters(
        self,
        query,
        *,
        status_tab: str | None,
        platform: ReviewPlatform | None,
        tone: str | None,
        period: str | None,
        is_paid: bool | None,
    ):
        if status_tab == "unanswered":
            query = query.filter(Review.response_text.is_(None))
        elif status_tab == "answered":
            query = query.filter(Review.response_text.isnot(None))
        elif status_tab == "in_progress":
            query = query.filter(Review.status == ReviewStatus.in_progress)
        elif status_tab == "escalated":
            query = query.filter(Review.status == ReviewStatus.escalated)
        if platform is not None:
            query = query.filter(Review.platform == platform)
        if tone == "neg":
            query = query.filter(Review.rating <= 3)
        elif tone == "pos":
            query = query.filter(Review.rating >= 4)
        if period:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS[period])).date()
            effective = func.coalesce(Review.review_date, func.date(Review.first_seen_at))
            query = query.filter(effective >= cutoff)
        if is_paid is not None:
            query = query.filter(Review.is_paid == is_paid)
        return query

    def _apply_sort(self, query, sort: str):
        if sort == "criticality":
            # Unanswered first (False sorts before True on both backends),
            # then worst rating, then newest.
            return query.order_by(
                Review.response_text.isnot(None),
                Review.rating.asc(),
                desc(Review.review_date).nullslast(),
                desc(Review.first_seen_at),
            )
        return query.order_by(desc(Review.review_date).nullslast(), desc(Review.first_seen_at))

    def summary(
        self,
        *,
        organization_id: UUID | None = None,
        rating: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        platform: ReviewPlatform | None = None,
        tone: str | None = None,
        period: str | None = None,
        is_paid: bool | None = None,
        aspect: str | None = None,
    ) -> dict:
        """Tab counters over the secondary-filtered set. Python aggregation keeps
        the aspect filter consistent with list_global (same in-memory matching)."""
        query = self.db.query(Review)
        if organization_id:
            query = query.filter(Review.organization_id == organization_id)
        query = self._apply_filters(query, rating, date_from, date_to, new_only=False)
        query = self._apply_feed_filters(
            query, status_tab=None, platform=platform, tone=tone, period=period, is_paid=is_paid
        )
        rows = [r for r in query.all() if not aspect or has_aspect(r, aspect)]

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        day_ago = now - timedelta(hours=24)
        return {
            "total": len(rows),
            "new_count": sum(1 for r in rows if _aware(r.first_seen_at) >= week_ago),
            "unanswered": sum(1 for r in rows if r.response_text is None),
            "in_progress": sum(1 for r in rows if r.status == ReviewStatus.in_progress),
            "escalated": sum(1 for r in rows if r.status == ReviewStatus.escalated),
            "answered": sum(1 for r in rows if r.response_text is not None),
            "overdue_24h": sum(
                1 for r in rows if r.response_text is None and _aware(r.first_seen_at) < day_ago
            ),
            "negative": sum(1 for r in rows if r.rating <= 3),
        }

    def aspects(
        self,
        *,
        period: str = "30d",
        organization_id: UUID | None = None,
        platform: ReviewPlatform | None = None,
        aspect: str | None = None,
    ) -> dict:
        """Aggregate problems JSONB per category for the aspects panel.

        Python aggregation over the loaded window (dashboard precedent) — no
        JSONB SQL, so SQLite tests keep working. Trend is always 90 days."""
        days = PERIOD_DAYS.get(period, 30)
        now = datetime.now(timezone.utc)
        today = now.date()
        cur_start = today - timedelta(days=days)
        prev_start = today - timedelta(days=days * 2)
        trend_start = today - timedelta(days=90)
        load_start = min(prev_start, trend_start)

        query = self.db.query(Review).filter(Review.problems.isnot(None))
        if organization_id:
            query = query.filter(Review.organization_id == organization_id)
        if platform is not None:
            query = query.filter(Review.platform == platform)

        def effective_date(r: Review) -> date:
            return r.review_date or _aware(r.first_seen_at).date()

        rows = [(r, effective_date(r)) for r in query.all()]
        rows = [(r, d) for r, d in rows if d >= load_start]

        current: dict[str, dict[str, int]] = {}
        previous: dict[str, int] = {}
        daily: dict[date, int] = {}
        for r, d in rows:
            categories = {p.get("category") for p in (r.problems or []) if p.get("category")}
            for cat in categories:
                if d >= cur_start:
                    bucket = current.setdefault(cat, {"mentions": 0, "pos": 0, "neu": 0, "neg": 0})
                    bucket["mentions"] += 1
                    key = {"positive": "pos", "negative": "neg"}.get(r.sentiment or "", "neu")
                    bucket[key] += 1
                elif d >= prev_start:
                    previous[cat] = previous.get(cat, 0) + 1
                if aspect and cat == aspect and d >= trend_start:
                    daily[d] = daily.get(d, 0) + 1

        aspects = []
        for cat, b in sorted(current.items(), key=lambda kv: -kv[1]["mentions"]):
            prev = previous.get(cat, 0)
            total = b["mentions"]
            aspects.append(
                {
                    "category": cat,
                    "label": cat.replace("_", " ").capitalize(),
                    "mentions": total,
                    "delta_pct": round((total - prev) / prev * 100) if prev else None,
                    "pos": round(b["pos"] / total * 100),
                    "neu": round(b["neu"] / total * 100),
                    "neg": round(b["neg"] / total * 100),
                }
            )

        trend = None
        if aspect:
            series = [
                {"date": (trend_start + timedelta(days=i)).isoformat(),
                 "count": daily.get(trend_start + timedelta(days=i), 0)}
                for i in range(91)
            ]
            trend = {"category": aspect, "days": 90, "series": series}
        return {"aspects": aspects, "trend": trend}
