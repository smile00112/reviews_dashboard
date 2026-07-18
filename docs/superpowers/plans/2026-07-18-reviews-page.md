# Reviews Page (GeoMonitor prototype) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/reviews` table with the prototype's feed page: status tabs, secondary filters, triage actions (status / paid flag) and an aspect-analysis panel.

**Architecture:** Extend `GET /api/reviews` with feed filters; add `GET /api/reviews/summary` (tab counters), `GET /api/reviews/aspects` (problems-JSONB aggregation), `PATCH /api/reviews/{id}` (admin-gated triage). Frontend is a client page whose single source of filter state is the URL; components live in `apps/web/components/reviews/`.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite tests / Postgres prod), Next.js App Router + Tailwind tokens already introduced by the overview feature. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-18-reviews-page-design.md`

## Global Constraints

- Read-only towards Yandex: no reply publishing anywhere. Stored `response_text` is display-only.
- Triage fields (`status`, `is_paid`, `paid_cost`) already exist on `Review` (feature 004) — never feed `content_hash`.
- No JSONB SQL operators — SQLite test backend must keep working; aspect matching is done in Python (precedent: `DashboardService` loads rows and aggregates in Python).
- Aspect taxonomy = `PROBLEM_CATEGORIES` keys from `apps/api/app/analysis/problems.py` (Russian snake_case keys, e.g. `качество_еды`). No LLM calls.
- Mutations require admin (`require_admin` from `app/api/deps.py`); reads stay open like the existing `/api/reviews`.
- API query param for the tab is `status` (values `all|unanswered|in_progress|escalated|answered`) — the overview attention feed already deep-links `/reviews?status=escalated`.
- Tab semantics: `answered` = `response_text IS NOT NULL`; `unanswered` = `response_text IS NULL`; `in_progress`/`escalated` = by `Review.status`. Tabs are filters and may overlap.
- Period filter values `24h|7d|30d|year` (cutoff days 1/7/30/365) applied to `coalesce(review_date, date(first_seen_at))`.
- Verification gate: `pytest -v` in `apps/api`, then `npm run lint` and `npx tsc --noEmit` in `apps/web`.

---

### Task 1: Feed filters + sort in `ReviewService.list_global` and `GET /api/reviews`

**Files:**
- Modify: `apps/api/app/services/review_service.py`
- Modify: `apps/api/app/schemas/review.py`
- Modify: `apps/api/app/api/reviews.py`
- Test: `apps/api/tests/test_reviews_feed_api.py` (create)

**Interfaces:**
- Produces: `ReviewService.list_global(..., status_tab, platform, tone, period, is_paid, aspect, sort)`; module-level `PERIOD_DAYS: dict[str, int]` and `has_aspect(review, aspect) -> bool` in `review_service.py`; `ReviewResponse` gains `status`, `is_paid`, `paid_cost`, `platform`. Later tasks (2–4) reuse `PERIOD_DAYS`, `has_aspect`, and the private `_apply_feed_filters`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_reviews_feed_api.py`:

```python
"""Feed filters for GET /api/reviews (reviews page rebuild).

Tab semantics: answered = has response_text, unanswered = none,
in_progress / escalated = by Review.status. Aspect filter matches
problems JSONB in Python (SQLite backend has no JSONB operators).
"""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _org(db, **kw):
    org = Organization(name=kw.pop("name", "Org"), **kw)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, hash_, rating=5, first_seen=None, review_date=None,
            response_text=None, status=None, platform=ReviewPlatform.yandex,
            is_paid=False, problems=None, sentiment=None):
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=platform,
        rating=rating,
        review_text="text",
        content_hash=hash_,
        first_seen_at=first_seen or NOW,
        last_seen_at=first_seen or NOW,
        response_text=response_text,
        response_first_seen_at=NOW if response_text else None,
        review_date=review_date,
        status=status,
        is_paid=is_paid,
        problems=problems,
        sentiment=sentiment,
    )
    db.add(r)
    db.commit()
    return r


def _ids(resp):
    return [item["id"] for item in resp.json()["items"]]


def test_status_tab_filters(client, db_session):
    org = _org(db_session)
    answered = _review(db_session, org, hash_="h1", response_text="спасибо")
    unanswered = _review(db_session, org, hash_="h2")
    in_progress = _review(db_session, org, hash_="h3", status=ReviewStatus.in_progress)
    escalated = _review(db_session, org, hash_="h4", status=ReviewStatus.escalated)

    assert str(answered.id) in _ids(client.get("/api/reviews?status=answered"))
    assert str(answered.id) not in _ids(client.get("/api/reviews?status=unanswered"))
    # escalated has no response -> also in unanswered (tabs overlap by design)
    assert str(escalated.id) in _ids(client.get("/api/reviews?status=unanswered"))
    assert _ids(client.get("/api/reviews?status=in_progress")) == [str(in_progress.id)]
    assert _ids(client.get("/api/reviews?status=escalated")) == [str(escalated.id)]
    assert len(_ids(client.get("/api/reviews?status=all"))) == 4


def test_platform_and_tone_filters(client, db_session):
    org = _org(db_session)
    ya_neg = _review(db_session, org, hash_="h1", rating=2, platform=ReviewPlatform.yandex)
    gis_pos = _review(db_session, org, hash_="h2", rating=5, platform=ReviewPlatform.gis2)

    assert _ids(client.get("/api/reviews?platform=gis2")) == [str(gis_pos.id)]
    assert _ids(client.get("/api/reviews?tone=neg")) == [str(ya_neg.id)]
    assert _ids(client.get("/api/reviews?tone=pos")) == [str(gis_pos.id)]


def test_period_filter_uses_review_date_with_first_seen_fallback(client, db_session):
    org = _org(db_session)
    fresh = _review(db_session, org, hash_="h1", review_date=NOW.date())
    old = _review(db_session, org, hash_="h2", review_date=(NOW - timedelta(days=200)).date())
    # No review_date -> falls back to first_seen_at date
    dateless_fresh = _review(db_session, org, hash_="h3", first_seen=NOW - timedelta(days=2))

    ids_30d = _ids(client.get("/api/reviews?period=30d"))
    assert str(fresh.id) in ids_30d
    assert str(dateless_fresh.id) in ids_30d
    assert str(old.id) not in ids_30d
    assert str(old.id) in _ids(client.get("/api/reviews?period=year"))


def test_is_paid_filter(client, db_session):
    org = _org(db_session)
    paid = _review(db_session, org, hash_="h1", is_paid=True)
    _review(db_session, org, hash_="h2")
    assert _ids(client.get("/api/reviews?is_paid=true")) == [str(paid.id)]


def test_aspect_filter_matches_problems_category(client, db_session):
    org = _org(db_session)
    with_aspect = _review(
        db_session, org, hash_="h1", rating=2,
        problems=[{"category": "ожидание", "description": "d", "keywords_found": ["долго ждать"], "severity": "low", "context": "c"}],
    )
    _review(db_session, org, hash_="h2", problems=[])
    _review(db_session, org, hash_="h3", problems=None)

    resp = client.get("/api/reviews?aspect=ожидание")
    assert _ids(resp) == [str(with_aspect.id)]
    assert resp.json()["total"] == 1


def test_sort_criticality_unanswered_low_rating_first(client, db_session):
    org = _org(db_session)
    answered_bad = _review(db_session, org, hash_="h1", rating=1, response_text="reply")
    unanswered_good = _review(db_session, org, hash_="h2", rating=5)
    unanswered_bad = _review(db_session, org, hash_="h3", rating=1)

    ids = _ids(client.get("/api/reviews?sort=criticality"))
    assert ids[0] == str(unanswered_bad.id)
    assert ids[1] == str(unanswered_good.id)
    assert ids[2] == str(answered_bad.id)


def test_response_includes_triage_fields(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", status=ReviewStatus.escalated, is_paid=True,
            platform=ReviewPlatform.gis2)
    item = client.get("/api/reviews").json()["items"][0]
    assert item["status"] == "escalated"
    assert item["is_paid"] is True
    assert item["paid_cost"] is None
    assert item["platform"] == "gis2"


def test_invalid_enum_params_return_422(client):
    assert client.get("/api/reviews?status=bogus").status_code == 422
    assert client.get("/api/reviews?tone=bogus").status_code == 422
    assert client.get("/api/reviews?period=bogus").status_code == 422
    assert client.get("/api/reviews?sort=bogus").status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `apps/api`): `pytest tests/test_reviews_feed_api.py -v`
Expected: FAIL — 422 for unknown params won't trigger (params ignored), triage fields missing from response.

- [ ] **Step 3: Implement service filters**

In `apps/api/app/services/review_service.py`:

Add to imports: `from sqlalchemy import desc, func` (replace the existing `from sqlalchemy import desc`) and add `ReviewStatus` to the enums import: `from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode`.

Add module-level constants/helpers after `logger = ...`:

```python
# Feed period presets (days back from now). "24h" is 1 day because review
# dates have day precision.
PERIOD_DAYS: dict[str, int] = {"24h": 1, "7d": 7, "30d": 30, "year": 365}


def has_aspect(review: Review, aspect: str) -> bool:
    """True when the review's problems JSONB contains the category.

    Python-side on purpose: the SQLite test backend has no JSONB operators.
    """
    return any(p.get("category") == aspect for p in (review.problems or []))
```

Replace `list_global` with:

```python
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
```

- [ ] **Step 4: Expose triage fields in the schema**

In `apps/api/app/schemas/review.py`, change the enums import to `from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode` and add to `ReviewResponse` (after `review_date`):

```python
    response_text: str | None
    # Internal triage (feature 004): DB-only workflow, nothing is published anywhere.
    status: ReviewStatus | None = None
    is_paid: bool = False
    paid_cost: int | None = None
    platform: ReviewPlatform | None = None
```

(`response_text` already exists — only the four new lines are added.)

- [ ] **Step 5: Wire the router params**

In `apps/api/app/api/reviews.py` replace `list_reviews` with:

```python
from app.models.enums import ReviewPlatform


@router.get("/api/reviews", response_model=ReviewListResponse)
def list_reviews(
    organization_id: UUID | None = None,
    rating: int | None = Query(default=None, ge=1, le=5),
    date_from: date | None = None,
    date_to: date | None = None,
    new_only: bool = False,
    status: str | None = Query(default=None, pattern="^(all|unanswered|in_progress|escalated|answered)$"),
    platform: ReviewPlatform | None = None,
    tone: str | None = Query(default=None, pattern="^(neg|pos)$"),
    period: str | None = Query(default=None, pattern="^(24h|7d|30d|year)$"),
    is_paid: bool | None = None,
    aspect: str | None = None,
    sort: str = Query(default="new", pattern="^(new|criticality)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewListResponse:
    rows, total = ReviewService(db).list_global(
        organization_id=organization_id,
        limit=limit,
        offset=offset,
        rating=rating,
        date_from=date_from,
        date_to=date_to,
        new_only=new_only,
        status_tab=None if status in (None, "all") else status,
        platform=platform,
        tone=tone,
        period=period,
        is_paid=is_paid,
        aspect=aspect,
        sort=sort,
    )
    items = [_to_review_response(review, org_name) for review, org_name in rows]
    return ReviewListResponse(items=items, total=total, limit=limit, offset=offset)
```

(Put the `ReviewPlatform` import at the top of the file with the other imports.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_reviews_feed_api.py -v`
Expected: all PASS.

Run the full suite to catch regressions: `pytest -v`
Expected: all PASS (existing `test_query_counts.py`, org API and dedup suites untouched).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/review_service.py apps/api/app/schemas/review.py apps/api/app/api/reviews.py apps/api/tests/test_reviews_feed_api.py
git commit -m "feat(api): feed filters, criticality sort and triage fields for GET /api/reviews"
```

---

### Task 2: `GET /api/reviews/summary`

**Files:**
- Modify: `apps/api/app/services/review_service.py`
- Modify: `apps/api/app/schemas/review.py`
- Modify: `apps/api/app/api/reviews.py`
- Test: `apps/api/tests/test_reviews_summary_api.py` (create)

**Interfaces:**
- Consumes: `_apply_feed_filters`, `has_aspect` from Task 1.
- Produces: `ReviewService.summary(...) -> dict` with keys `total,new_count,unanswered,in_progress,escalated,answered,overdue_24h,negative`; schema `ReviewSummaryResponse`; endpoint `GET /api/reviews/summary`. Frontend (Task 5) mirrors this shape as `ReviewsSummary`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_reviews_summary_api.py`:

```python
"""Tab counters for the reviews page. Counters respect the secondary filters
(platform/tone/period/org/aspect) but never the status tab itself."""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _org(db):
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, hash_, rating=5, first_seen=None, response_text=None,
            status=None, platform=ReviewPlatform.yandex):
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=platform,
        rating=rating,
        review_text="text",
        content_hash=hash_,
        first_seen_at=first_seen or NOW,
        last_seen_at=first_seen or NOW,
        response_text=response_text,
        response_first_seen_at=NOW if response_text else None,
        status=status,
    )
    db.add(r)
    db.commit()
    return r


def test_summary_counts(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", response_text="ok")                     # answered
    _review(db_session, org, hash_="h2", rating=2)                               # unanswered, negative, fresh
    _review(db_session, org, hash_="h3", rating=1, first_seen=NOW - timedelta(hours=30))  # unanswered overdue, negative
    _review(db_session, org, hash_="h4", status=ReviewStatus.in_progress)        # unanswered, in progress
    _review(db_session, org, hash_="h5", status=ReviewStatus.escalated,
            first_seen=NOW - timedelta(days=10))                                 # unanswered overdue, not "new"

    body = client.get("/api/reviews/summary").json()
    assert body["total"] == 5
    assert body["answered"] == 1
    assert body["unanswered"] == 4
    assert body["in_progress"] == 1
    assert body["escalated"] == 1
    assert body["overdue_24h"] == 2      # h3, h5
    assert body["negative"] == 2         # h2, h3
    assert body["new_count"] == 4        # first_seen within 7d: h1,h2,h3,h4


def test_summary_respects_secondary_filters(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", rating=2, platform=ReviewPlatform.yandex)
    _review(db_session, org, hash_="h2", rating=5, platform=ReviewPlatform.gis2)

    body = client.get("/api/reviews/summary?platform=gis2").json()
    assert body["total"] == 1
    assert body["negative"] == 0


def test_summary_empty_db_zeroes(client):
    body = client.get("/api/reviews/summary").json()
    assert body == {
        "total": 0, "new_count": 0, "unanswered": 0, "in_progress": 0,
        "escalated": 0, "answered": 0, "overdue_24h": 0, "negative": 0,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reviews_summary_api.py -v`
Expected: FAIL with 404 (endpoint does not exist).

- [ ] **Step 3: Implement service + schema + endpoint**

In `apps/api/app/services/review_service.py` add a module-level helper after `has_aspect`:

```python
def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware. Normalize to UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
```

Add a method to `ReviewService`:

```python
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
```

In `apps/api/app/schemas/review.py` add:

```python
class ReviewSummaryResponse(BaseModel):
    total: int
    new_count: int
    unanswered: int
    in_progress: int
    escalated: int
    answered: int
    overdue_24h: int
    negative: int
```

In `apps/api/app/api/reviews.py` add (import `ReviewSummaryResponse` from `app.schemas.review`):

```python
@router.get("/api/reviews/summary", response_model=ReviewSummaryResponse)
def reviews_summary(
    organization_id: UUID | None = None,
    rating: int | None = Query(default=None, ge=1, le=5),
    date_from: date | None = None,
    date_to: date | None = None,
    platform: ReviewPlatform | None = None,
    tone: str | None = Query(default=None, pattern="^(neg|pos)$"),
    period: str | None = Query(default=None, pattern="^(24h|7d|30d|year)$"),
    is_paid: bool | None = None,
    aspect: str | None = None,
    db: Session = Depends(get_db),
) -> ReviewSummaryResponse:
    data = ReviewService(db).summary(
        organization_id=organization_id,
        rating=rating,
        date_from=date_from,
        date_to=date_to,
        platform=platform,
        tone=tone,
        period=period,
        is_paid=is_paid,
        aspect=aspect,
    )
    return ReviewSummaryResponse(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reviews_summary_api.py tests/test_reviews_feed_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/review_service.py apps/api/app/schemas/review.py apps/api/app/api/reviews.py apps/api/tests/test_reviews_summary_api.py
git commit -m "feat(api): reviews summary endpoint with tab counters"
```

---

### Task 3: `GET /api/reviews/aspects`

**Files:**
- Modify: `apps/api/app/services/review_service.py`
- Modify: `apps/api/app/schemas/review.py`
- Modify: `apps/api/app/api/reviews.py`
- Test: `apps/api/tests/test_reviews_aspects_api.py` (create)

**Interfaces:**
- Consumes: `PERIOD_DAYS`, `_aware` from earlier tasks; `Review.problems` / `Review.sentiment` columns (feature 002).
- Produces: `ReviewService.aspects(period, organization_id, platform, aspect) -> dict`; schemas `AspectStat`, `AspectTrend`, `AspectsResponse`; endpoint `GET /api/reviews/aspects`. Frontend (Task 5) mirrors `AspectsResponse`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_reviews_aspects_api.py`:

```python
"""Aspect aggregation from problems JSONB (fixed local taxonomy, no LLM).

delta_pct compares the selected window against the previous window of equal
length; None when the previous window had zero mentions."""

from datetime import datetime, timedelta, timezone

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _org(db):
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _review(db, org, *, hash_, days_ago, categories, sentiment="negative", rating=2):
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex,
        rating=rating,
        review_text="text",
        content_hash=hash_,
        first_seen_at=NOW - timedelta(days=days_ago),
        last_seen_at=NOW,
        review_date=(NOW - timedelta(days=days_ago)).date(),
        sentiment=sentiment,
        problems=[
            {"category": c, "description": "d", "keywords_found": ["k"], "severity": "low", "context": ""}
            for c in categories
        ],
    )
    db.add(r)
    db.commit()
    return r


def test_aspects_mentions_delta_and_sentiment(client, db_session):
    org = _org(db_session)
    # current 30d window: 2 mentions of "ожидание" (1 neg, 1 pos)
    _review(db_session, org, hash_="h1", days_ago=5, categories=["ожидание"], sentiment="negative")
    _review(db_session, org, hash_="h2", days_ago=10, categories=["ожидание"], sentiment="positive", rating=4)
    # previous window (30..60 days back): 1 mention
    _review(db_session, org, hash_="h3", days_ago=45, categories=["ожидание"])
    # different aspect, current window only -> delta None
    _review(db_session, org, hash_="h4", days_ago=3, categories=["чистота"])

    body = client.get("/api/reviews/aspects?period=30d").json()
    by_cat = {a["category"]: a for a in body["aspects"]}

    waiting = by_cat["ожидание"]
    assert waiting["mentions"] == 2
    assert waiting["delta_pct"] == 100          # 2 vs 1
    assert waiting["pos"] == 50 and waiting["neg"] == 50 and waiting["neu"] == 0
    assert waiting["label"] == "Ожидание"

    clean = by_cat["чистота"]
    assert clean["mentions"] == 1
    assert clean["delta_pct"] is None           # nothing in previous window
    assert body["trend"] is None


def test_aspects_trend_series_90_days(client, db_session):
    org = _org(db_session)
    _review(db_session, org, hash_="h1", days_ago=1, categories=["ожидание"])
    _review(db_session, org, hash_="h2", days_ago=1, categories=["ожидание"])
    _review(db_session, org, hash_="h3", days_ago=80, categories=["ожидание"])
    _review(db_session, org, hash_="h4", days_ago=100, categories=["ожидание"])  # outside 90d

    body = client.get("/api/reviews/aspects?period=30d&aspect=ожидание").json()
    trend = body["trend"]
    assert trend["category"] == "ожидание"
    assert trend["days"] == 90
    assert len(trend["series"]) == 91           # today + 90 days back, zero-filled
    assert sum(p["count"] for p in trend["series"]) == 3
    yesterday = (NOW - timedelta(days=1)).date().isoformat()
    assert {"date": yesterday, "count": 2} in trend["series"]


def test_aspects_empty_db(client):
    body = client.get("/api/reviews/aspects").json()
    assert body == {"aspects": [], "trend": None}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reviews_aspects_api.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Implement service + schema + endpoint**

In `apps/api/app/services/review_service.py` add to `ReviewService`:

```python
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
```

In `apps/api/app/schemas/review.py` add:

```python
class AspectStat(BaseModel):
    category: str
    label: str
    mentions: int
    delta_pct: int | None
    pos: int
    neu: int
    neg: int


class AspectTrendPoint(BaseModel):
    date: date
    count: int


class AspectTrend(BaseModel):
    category: str
    days: int
    series: list[AspectTrendPoint]


class AspectsResponse(BaseModel):
    aspects: list[AspectStat]
    trend: AspectTrend | None = None
```

In `apps/api/app/api/reviews.py` add (import `AspectsResponse`):

```python
@router.get("/api/reviews/aspects", response_model=AspectsResponse)
def reviews_aspects(
    period: str = Query(default="30d", pattern="^(24h|7d|30d|year)$"),
    organization_id: UUID | None = None,
    platform: ReviewPlatform | None = None,
    aspect: str | None = None,
    db: Session = Depends(get_db),
) -> AspectsResponse:
    data = ReviewService(db).aspects(
        period=period, organization_id=organization_id, platform=platform, aspect=aspect
    )
    return AspectsResponse(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reviews_aspects_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/review_service.py apps/api/app/schemas/review.py apps/api/app/api/reviews.py apps/api/tests/test_reviews_aspects_api.py
git commit -m "feat(api): aspects aggregation endpoint for reviews page"
```

---

### Task 4: `PATCH /api/reviews/{id}` (admin triage)

**Files:**
- Modify: `apps/api/app/services/review_service.py`
- Modify: `apps/api/app/schemas/review.py`
- Modify: `apps/api/app/api/reviews.py`
- Test: `apps/api/tests/test_reviews_patch_api.py` (create)

**Interfaces:**
- Consumes: `require_admin` from `app/api/deps.py`; `admin_client` / `operator_client` fixtures from `conftest.py`.
- Produces: `ReviewService.update_triage(review_id, data: dict) -> Review | None`; schema `ReviewPatchRequest`; endpoint `PATCH /api/reviews/{review_id}` returning `ReviewResponse`. Frontend (Task 5) calls it as `patchReview`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_reviews_patch_api.py`:

```python
"""Internal triage mutations (status / paid flag). Admin-gated like every other
mutation. Nothing is ever published to external platforms."""

import uuid
from datetime import datetime, timezone

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _seed_review(db):
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex,
        rating=1,
        review_text="text",
        content_hash="h1",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_patch_requires_auth(client, db_session):
    r = _seed_review(db_session)
    resp = client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    assert resp.status_code == 401


def test_patch_requires_admin_role(operator_client, db_session):
    r = _seed_review(db_session)
    resp = operator_client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    assert resp.status_code == 403


def test_patch_status_and_paid(admin_client, db_session):
    r = _seed_review(db_session)
    resp = admin_client.patch(
        f"/api/reviews/{r.id}",
        json={"status": "in_progress", "is_paid": True, "paid_cost": 570},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["is_paid"] is True
    assert body["paid_cost"] == 570
    assert body["organization_name"] == "Org"

    # Partial update: only reset paid_cost, everything else untouched.
    resp = admin_client.patch(f"/api/reviews/{r.id}", json={"paid_cost": None})
    body = resp.json()
    assert body["paid_cost"] is None
    assert body["status"] == "in_progress"
    assert body["is_paid"] is True


def test_patch_dedup_hash_untouched(admin_client, db_session):
    r = _seed_review(db_session)
    before = r.content_hash
    admin_client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    db_session.refresh(r)
    assert r.content_hash == before


def test_patch_unknown_review_404(admin_client):
    resp = admin_client.patch(f"/api/reviews/{uuid.uuid4()}", json={"status": "escalated"})
    assert resp.status_code == 404


def test_patch_invalid_status_422(admin_client, db_session):
    r = _seed_review(db_session)
    resp = admin_client.patch(f"/api/reviews/{r.id}", json={"status": "published"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reviews_patch_api.py -v`
Expected: FAIL with 405/404 (no PATCH route).

- [ ] **Step 3: Implement service + schema + endpoint**

In `apps/api/app/services/review_service.py` add to `ReviewService`:

```python
    def update_triage(self, review_id: UUID, data: dict) -> Review | None:
        """Apply internal triage fields (status / is_paid / paid_cost) only.

        `data` must come from model_dump(exclude_unset=True) so an absent field
        is distinguishable from an explicit null (paid_cost reset)."""
        review = self.db.query(Review).filter(Review.id == review_id).first()
        if review is None:
            return None
        for field in ("status", "is_paid", "paid_cost"):
            if field in data:
                setattr(review, field, data[field])
        self.db.commit()
        self.db.refresh(review)
        return review
```

In `apps/api/app/schemas/review.py` add:

```python
class ReviewPatchRequest(BaseModel):
    status: ReviewStatus | None = None
    is_paid: bool | None = None
    paid_cost: int | None = Field(default=None, ge=0)
```

In `apps/api/app/api/reviews.py` add (imports: `ReviewPatchRequest`, `require_admin` from `app.api.deps`, `User` from `app.models.user`):

```python
@router.patch("/api/reviews/{review_id}", response_model=ReviewResponse)
def patch_review(
    review_id: UUID,
    payload: ReviewPatchRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ReviewResponse:
    review = ReviewService(db).update_triage(review_id, payload.model_dump(exclude_unset=True))
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    org = OrganizationService(db).get(review.organization_id)
    return _to_review_response(review, org.name if org else None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reviews_patch_api.py -v`
Expected: all PASS.

Full backend gate: `pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/review_service.py apps/api/app/schemas/review.py apps/api/app/api/reviews.py apps/api/tests/test_reviews_patch_api.py
git commit -m "feat(api): admin-gated PATCH /api/reviews/{id} for internal triage"
```

---

### Task 5: Frontend types + API client

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`

**Interfaces:**
- Consumes: endpoints from Tasks 1–4.
- Produces (used by Tasks 6–9): types `ReviewStatus`, `ReviewPlatform`, `StatusTab`, `ReviewTone`, `ReviewPeriod`, `ReviewSort`, `ReviewProblem`, `ReviewsSummary`, `AspectStat`, `AspectsResponse`, extended `Review`; functions `listReviews(params: ReviewFeedParams)` (existing, unchanged signature), `getReviewsSummary(params)`, `getReviewAspects(params)`, `patchReview(id, payload)`.

- [ ] **Step 1: Extend `apps/web/lib/types.ts`**

Add after the `Review` interface region (and extend `Review` itself):

```ts
export type ReviewStatus = "new" | "in_progress" | "answered" | "escalated";
export type ReviewPlatform = "yandex" | "google" | "gis2";
export type StatusTab = "all" | "unanswered" | "in_progress" | "escalated" | "answered";
export type ReviewTone = "neg" | "pos";
export type ReviewPeriod = "24h" | "7d" | "30d" | "year";
export type ReviewSort = "new" | "criticality";

export interface ReviewProblem {
  category: string;
  description: string;
  keywords_found: string[];
  severity: string;
  context: string;
}

export interface ReviewsSummary {
  total: number;
  new_count: number;
  unanswered: number;
  in_progress: number;
  escalated: number;
  answered: number;
  overdue_24h: number;
  negative: number;
}

export interface AspectStat {
  category: string;
  label: string;
  mentions: number;
  delta_pct: number | null;
  pos: number;
  neu: number;
  neg: number;
}

export interface AspectTrend {
  category: string;
  days: number;
  series: { date: string; count: number }[];
}

export interface AspectsResponse {
  aspects: AspectStat[];
  trend: AspectTrend | null;
}
```

Extend the existing `Review` interface with (after `response_text`):

```ts
  response_first_seen_at: string | null;
  status: ReviewStatus | null;
  is_paid: boolean;
  paid_cost: number | null;
  platform: ReviewPlatform | null;
  sentiment: string | null;
  sentiment_score: number | null;
  problems: ReviewProblem[] | null;
```

- [ ] **Step 2: Extend `apps/web/lib/api.ts`**

Add to the type import from `./types`: `AspectsResponse, ReviewStatus, ReviewsSummary`.

Add below `listReviews` (which stays as-is — it already forwards arbitrary params):

```ts
export async function getReviewsSummary(
  params: Record<string, string | number | boolean | undefined> = {},
): Promise<ReviewsSummary> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ReviewsSummary>(`/api/reviews/summary${suffix}`);
}

export async function getReviewAspects(
  params: Record<string, string | undefined> = {},
): Promise<AspectsResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AspectsResponse>(`/api/reviews/aspects${suffix}`);
}

export async function patchReview(
  id: string,
  payload: { status?: ReviewStatus; is_paid?: boolean; paid_cost?: number | null },
): Promise<Review> {
  return request<Review>(`/api/reviews/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 3: Verify compile**

Run (from `apps/web`): `npx tsc --noEmit`
Expected: no errors. (`components/reviews-table.tsx` and the org detail page keep compiling — the `Review` extension is additive.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts
git commit -m "feat(web): reviews feed types and API client (summary, aspects, patch)"
```

---

### Task 6: `StatusTabs` + `ReviewFilters` components

**Files:**
- Create: `apps/web/components/reviews/status-tabs.tsx`
- Create: `apps/web/components/reviews/review-filters.tsx`

**Interfaces:**
- Consumes: types from Task 5; `Organization` type.
- Produces: `<StatusTabs tab summary onTab />` and `<ReviewFilters tone period platform organizationId paidOnly orgs onChange onReset />` where `onChange(patch: Partial<FeedFilterState>)`; exported `interface FeedFilterState { tone?: ReviewTone; period?: ReviewPeriod; platform?: ReviewPlatform; organizationId?: string; paidOnly?: boolean }`. Task 9 wires them to the URL.

- [ ] **Step 1: Create `apps/web/components/reviews/status-tabs.tsx`**

```tsx
"use client";

import type { ReviewsSummary, StatusTab } from "@/lib/types";

const TABS: { key: StatusTab; label: string; count: (s: ReviewsSummary) => number; danger?: boolean }[] = [
  { key: "all", label: "Все", count: (s) => s.total },
  { key: "unanswered", label: "Не отвечено", count: (s) => s.unanswered, danger: true },
  { key: "in_progress", label: "В работе", count: (s) => s.in_progress },
  { key: "escalated", label: "Эскалированные", count: (s) => s.escalated, danger: true },
  { key: "answered", label: "Отвечено", count: (s) => s.answered },
];

export function StatusTabs({
  tab,
  summary,
  onTab,
}: {
  tab: StatusTab;
  summary: ReviewsSummary | null;
  onTab: (tab: StatusTab) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {TABS.map((t) => {
        const active = tab === t.key;
        const count = summary ? t.count(summary) : null;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onTab(t.key)}
            className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2.5 text-[13px] font-medium transition-colors ${
              active
                ? "border-accent bg-surface-3 text-text"
                : "border-border bg-surface-2 text-text-dim hover:border-text-faint hover:text-text"
            }`}
          >
            {t.label}
            {count !== null && (
              <span
                className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                  t.danger && count > 0 ? "bg-bad/15 text-bad" : "bg-surface-3 text-text-faint"
                }`}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Create `apps/web/components/reviews/review-filters.tsx`**

```tsx
"use client";

import type { Organization, ReviewPeriod, ReviewPlatform, ReviewTone, ReviewsSummary } from "@/lib/types";

export interface FeedFilterState {
  tone?: ReviewTone;
  period?: ReviewPeriod;
  platform?: ReviewPlatform;
  organizationId?: string;
  paidOnly?: boolean;
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] transition-colors ${
        active
          ? "border-accent bg-surface-3 text-text"
          : "border-border bg-surface-2 text-text-dim hover:border-text-faint hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

const PERIODS: { key: ReviewPeriod; label: string }[] = [
  { key: "24h", label: "24ч" },
  { key: "7d", label: "7д" },
  { key: "30d", label: "30д" },
  { key: "year", label: "Год" },
];

const PLATFORMS: { key: ReviewPlatform; label: string }[] = [
  { key: "yandex", label: "Я" },
  { key: "google", label: "G" },
  { key: "gis2", label: "2Г" },
];

export function ReviewFilters({
  tone,
  period,
  platform,
  organizationId,
  paidOnly,
  orgs,
  summary,
  onChange,
  onReset,
}: FeedFilterState & {
  orgs: Organization[];
  summary: ReviewsSummary | null;
  onChange: (patch: FeedFilterState) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-surface-1 p-3 text-[12px]">
      <div className="flex items-center gap-1.5">
        <span className="text-text-faint">Тональность:</span>
        <Chip active={!tone} onClick={() => onChange({ tone: undefined })}>Все</Chip>
        <Chip active={tone === "neg"} onClick={() => onChange({ tone: "neg" })}>
          😞 Негатив 1–3★
          {summary && summary.negative > 0 && (
            <span className="rounded bg-bad/15 px-1 font-mono text-[10px] text-bad">{summary.negative}</span>
          )}
        </Chip>
        <Chip active={tone === "pos"} onClick={() => onChange({ tone: "pos" })}>😊 Позитив 4–5★</Chip>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-text-faint">Период:</span>
        {PERIODS.map((p) => (
          <Chip
            key={p.key}
            active={period === p.key}
            onClick={() => onChange({ period: period === p.key ? undefined : p.key })}
          >
            {p.label}
          </Chip>
        ))}
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-text-faint">Площадка:</span>
        <Chip active={!platform} onClick={() => onChange({ platform: undefined })}>Все</Chip>
        {PLATFORMS.map((p) => (
          <Chip key={p.key} active={platform === p.key} onClick={() => onChange({ platform: p.key })}>
            {p.label}
          </Chip>
        ))}
      </div>
      <select
        value={organizationId ?? ""}
        onChange={(e) => onChange({ organizationId: e.target.value || undefined })}
        className="rounded-lg border border-border bg-surface-2 px-2 py-1 text-[12px] text-text-dim"
      >
        <option value="">Все локации</option>
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.name ?? org.yandex_url ?? org.gis2_url ?? org.id}
          </option>
        ))}
      </select>
      <Chip active={!!paidOnly} onClick={() => onChange({ paidOnly: paidOnly ? undefined : true })}>
        💎 Покупные
      </Chip>
      <button type="button" onClick={onReset} className="ml-auto text-[12px] text-text-faint hover:text-text">
        Сбросить
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Verify compile**

Run: `npx tsc --noEmit`
Expected: no errors (components not yet imported anywhere — that's fine).

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/reviews/status-tabs.tsx apps/web/components/reviews/review-filters.tsx
git commit -m "feat(web): status tabs and secondary filter chips for reviews page"
```

---

### Task 7: `ReviewCard` component

**Files:**
- Create: `apps/web/components/reviews/review-card.tsx`

**Interfaces:**
- Consumes: `Review`, `ReviewStatus` types; `patchReview` from `lib/api`.
- Produces: `<ReviewCard review onPatched onAspect />` — `onPatched(updated: Review)` replaces the item in the page's list; `onAspect(category: string)` sets the aspect filter. Task 9 consumes both.

- [ ] **Step 1: Create `apps/web/components/reviews/review-card.tsx`**

```tsx
"use client";

import { useState } from "react";
import type { Review, ReviewStatus } from "@/lib/types";
import { patchReview } from "@/lib/api";

const PLATFORM_TAG: Record<string, { label: string; cls: string }> = {
  yandex: { label: "Я", cls: "bg-[#fc3f1d]/15 text-[#ff6b4d]" },
  google: { label: "G", cls: "bg-[#4285f4]/15 text-[#7ab0ff]" },
  gis2: { label: "2Г", cls: "bg-[#2dbe64]/15 text-[#4fd786]" },
};

function stars(rating: number): string {
  return "★".repeat(rating) + "☆".repeat(5 - rating);
}

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const h = Math.floor(ms / 3_600_000);
  if (h < 1) return "меньше часа назад";
  if (h < 24) return `${h} ч назад`;
  const d = Math.floor(h / 24);
  return `${d} дн назад`;
}

function ageHours(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
}

function StatusBadge({ review }: { review: Review }) {
  if (review.status === "escalated")
    return <span className="rounded bg-bad/15 px-2 py-0.5 text-[10.5px] font-semibold text-bad">🔥 ЭСКАЛИРОВАНО</span>;
  if (review.status === "in_progress")
    return <span className="rounded bg-accent/15 px-2 py-0.5 text-[10.5px] font-semibold text-accent">В РАБОТЕ</span>;
  if (review.response_text)
    return <span className="rounded bg-good/15 px-2 py-0.5 text-[10.5px] font-semibold text-good">ОТВЕЧЕН</span>;
  return (
    <span className="rounded bg-bad/15 px-2 py-0.5 text-[10.5px] font-semibold text-bad">
      БЕЗ ОТВЕТА · {ageHours(review.first_seen_at)}ч
    </span>
  );
}

export function ReviewCard({
  review,
  onPatched,
  onAspect,
}: {
  review: Review;
  onPatched: (updated: Review) => void;
  onAspect: (category: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<string>(review.paid_cost?.toString() ?? "");

  async function patch(payload: Parameters<typeof patchReview>[1]) {
    setBusy(true);
    setError(null);
    try {
      onPatched(await patchReview(review.id, payload));
    } catch (e) {
      const status = (e as Error & { status?: number }).status;
      setError(
        status === 401 || status === 403
          ? "Нужны права администратора"
          : "Не удалось сохранить",
      );
    } finally {
      setBusy(false);
    }
  }

  const tag = review.platform ? PLATFORM_TAG[review.platform] : null;
  const negative = review.rating <= 3;

  return (
    <div
      className={`rounded-xl border bg-surface-1 p-4 ${
        review.status === "escalated" ? "border-bad/40" : review.response_text ? "border-border" : "border-bad/20"
      }`}
    >
      <div className="flex items-center justify-between gap-2 text-[12.5px]">
        <div className="flex items-center gap-2">
          <b>{review.author_name ?? "Аноним"}</b>
          <span className="text-text-faint">· {review.organization_name ?? "—"}</span>
          {tag && <span className={`rounded px-1.5 py-0.5 font-mono text-[10.5px] ${tag.cls}`}>{tag.label}</span>}
        </div>
        <span className="text-text-faint">{review.review_date_text ?? relTime(review.first_seen_at)}</span>
      </div>

      <div className={`mt-1.5 font-mono text-[13px] ${negative ? "text-bad" : "text-accent"}`}>
        {stars(review.rating)} {review.rating}.0
      </div>

      <p className="mt-2 text-[13.5px] leading-relaxed text-text">{review.review_text}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-text-dim">
        <StatusBadge review={review} />
        {review.sentiment_score !== null && (
          <span>
            Тональность:{" "}
            <b className={review.sentiment === "negative" ? "text-bad" : review.sentiment === "positive" ? "text-good" : ""}>
              {review.sentiment_score > 0 ? "+" : ""}
              {review.sentiment_score.toFixed(2)}
            </b>
          </span>
        )}
        {(review.problems?.length ?? 0) > 0 && (
          <span className="flex flex-wrap items-center gap-1">
            Аспекты:
            {review.problems!.map((p) => (
              <button
                key={p.category}
                type="button"
                onClick={() => onAspect(p.category)}
                className="rounded bg-surface-3 px-1.5 py-0.5 text-[10.5px] text-text-dim hover:text-text"
                title="Отфильтровать ленту по аспекту"
              >
                {p.category.replace(/_/g, " ")}
              </button>
            ))}
          </span>
        )}
      </div>

      {review.response_text && (
        <div className="mt-3 rounded-lg border-l-2 border-accent/50 bg-surface-2 p-3 text-[12.5px]">
          <div className="mb-1 flex justify-between text-[11px] text-text-faint">
            <span>↪ Ответ компании</span>
            {review.response_first_seen_at && <span>замечен {relTime(review.response_first_seen_at)}</span>}
          </div>
          <div className="text-text-dim">{review.response_text}</div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
        {review.status !== "in_progress" && review.status !== "escalated" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => patch({ status: "in_progress" })}
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-text-dim hover:text-text disabled:opacity-50"
          >
            В работу
          </button>
        )}
        {review.status !== "escalated" ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => patch({ status: "escalated" })}
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-text-dim hover:text-bad disabled:opacity-50"
          >
            🔥 Эскалировать
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => patch({ status: review.response_text ? "answered" : "new" })}
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-text-dim hover:text-text disabled:opacity-50"
          >
            ↩ Снять эскалацию
          </button>
        )}
        <label className="ml-1 inline-flex cursor-pointer items-center gap-1.5 text-text-dim">
          <input
            type="checkbox"
            checked={review.is_paid}
            disabled={busy}
            onChange={(e) => patch({ is_paid: e.target.checked })}
          />
          💎 Покупной
        </label>
        {review.is_paid && (
          <span className="inline-flex items-center gap-1 text-text-faint">
            <input
              type="number"
              min={0}
              value={cost}
              placeholder="₽"
              disabled={busy}
              onChange={(e) => setCost(e.target.value)}
              onBlur={() => {
                const parsed = cost === "" ? null : Number(cost);
                if (parsed !== review.paid_cost) patch({ paid_cost: parsed });
              }}
              className="w-20 rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[12px]"
            />
            ₽
          </span>
        )}
        {error && <span className="text-[11.5px] text-bad">{error}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify compile**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/components/reviews/review-card.tsx
git commit -m "feat(web): review card with triage actions and display-only company reply"
```

---

### Task 8: `AspectsPanel` component (table + trend SVG)

**Files:**
- Create: `apps/web/components/reviews/aspects-panel.tsx`

**Interfaces:**
- Consumes: `AspectsResponse`, `AspectStat` types; `Panel` from `components/dashboard/panel`.
- Produces: `<AspectsPanel data activeAspect onAspect />` — `onAspect(category: string | null)` toggles the feed's aspect filter. Task 9 consumes it.

- [ ] **Step 1: Create `apps/web/components/reviews/aspects-panel.tsx`**

```tsx
"use client";

import type { AspectsResponse } from "@/lib/types";
import { Panel } from "@/components/dashboard/panel";

function SentimentBar({ pos, neu, neg }: { pos: number; neu: number; neg: number }) {
  const total = pos + neu + neg || 1;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="inline-flex h-2 w-[100px] overflow-hidden rounded bg-surface-3">
      <div className="h-full bg-good" style={{ width: w(pos) }} />
      <div className="h-full bg-text-faint" style={{ width: w(neu) }} />
      <div className="h-full bg-bad" style={{ width: w(neg) }} />
    </div>
  );
}

function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="text-text-faint">новый</span>;
  if (value === 0) return <span className="text-text-faint">— 0%</span>;
  // Growth of complaint mentions is bad, decline is good.
  return (
    <span className={value > 0 ? "text-bad" : "text-good"}>
      {value > 0 ? "▲ +" : "▼ "}
      {value}%
    </span>
  );
}

function TrendChart({ series }: { series: { date: string; count: number }[] }) {
  const max = Math.max(...series.map((p) => p.count), 1);
  const W = 460;
  const H = 80;
  const step = W / (series.length - 1 || 1);
  const points = series
    .map((p, i) => `${(i * step).toFixed(1)},${(H - (p.count / max) * (H - 6) - 3).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[90px] w-full" preserveAspectRatio="none" role="img">
      <polyline points={points} fill="none" stroke="var(--color-accent, #d4ff3a)" strokeWidth="1.5" />
    </svg>
  );
}

export function AspectsPanel({
  data,
  activeAspect,
  onAspect,
}: {
  data: AspectsResponse | null;
  activeAspect: string | null;
  onAspect: (category: string | null) => void;
}) {
  return (
    <Panel title="Аспектный анализ" meta="Привязан к фильтру периода · клик по строке → фильтр ленты">
      {!data || data.aspects.length === 0 ? (
        <div className="py-10 text-center text-text-faint">Нет данных за период</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-text-faint">
                <th className="border-b border-border px-3 py-2.5 text-left">Аспект</th>
                <th className="border-b border-border px-3 py-2.5 text-left">Упом.</th>
                <th className="border-b border-border px-3 py-2.5 text-left">Δ за период</th>
                <th className="border-b border-border px-3 py-2.5 text-left">Тональность</th>
              </tr>
            </thead>
            <tbody>
              {data.aspects.map((a) => (
                <tr
                  key={a.category}
                  onClick={() => onAspect(activeAspect === a.category ? null : a.category)}
                  className={`cursor-pointer hover:bg-surface-2 ${
                    activeAspect === a.category ? "bg-surface-2" : ""
                  }`}
                  title="Кликните, чтобы отфильтровать ленту"
                >
                  <td className="border-b border-border px-3 py-3 font-semibold">{a.label}</td>
                  <td className="border-b border-border px-3 py-3">{a.mentions}</td>
                  <td className="border-b border-border px-3 py-3 font-mono text-[11px]">
                    <Delta value={a.delta_pct} />
                  </td>
                  <td className="border-b border-border px-3 py-3">
                    <SentimentBar pos={a.pos} neu={a.neu} neg={a.neg} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-3.5 flex flex-wrap gap-3.5 text-[11px] text-text-dim">
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-good align-middle" />Позитив</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-text-faint align-middle" />Нейтрально</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-bad align-middle" />Негатив</span>
      </div>
      {data?.trend && (
        <div className="mt-4 rounded-lg border border-border bg-surface-2 p-3">
          <div className="mb-1 flex items-center justify-between text-[12px]">
            <span className="font-semibold">
              Динамика «{data.aspects.find((a) => a.category === data.trend!.category)?.label ?? data.trend.category}» за 90 дней
            </span>
          </div>
          <TrendChart series={data.trend.series} />
        </div>
      )}
    </Panel>
  );
}
```

- [ ] **Step 2: Verify compile**

Run: `npx tsc --noEmit`
Expected: no errors. If `Panel`'s props differ (check `apps/web/components/dashboard/panel.tsx` — it takes `title`, `meta`, `children`), adapt the call to its actual signature.

- [ ] **Step 3: Commit**

```bash
git add apps/web/components/reviews/aspects-panel.tsx
git commit -m "feat(web): aspects panel with sentiment bars and 90d trend chart"
```

---

### Task 9: Rewrite `/reviews` page (URL-driven state)

**Files:**
- Modify: `apps/web/app/(dashboard)/reviews/page.tsx` (full rewrite)

**Interfaces:**
- Consumes: everything from Tasks 5–8.
- Produces: page reading/writing URL params `status, tone, period, platform, organization_id, is_paid, aspect, sort, rating, new_only`. Deep links `/reviews?rating=1` and `/reviews?status=escalated` from the overview attention feed keep working.

- [ ] **Step 1: Rewrite the page**

Replace `apps/web/app/(dashboard)/reviews/page.tsx` with:

```tsx
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getReviewAspects,
  getReviewsSummary,
  listOrganizations,
  listReviews,
} from "@/lib/api";
import type {
  AspectsResponse,
  Organization,
  Review,
  ReviewPeriod,
  ReviewPlatform,
  ReviewSort,
  ReviewTone,
  ReviewsSummary,
  StatusTab,
} from "@/lib/types";
import { StatusTabs } from "@/components/reviews/status-tabs";
import { ReviewFilters, type FeedFilterState } from "@/components/reviews/review-filters";
import { ReviewCard } from "@/components/reviews/review-card";
import { AspectsPanel } from "@/components/reviews/aspects-panel";

const PAGE_SIZE = 50;

function ReviewsContent() {
  const router = useRouter();
  const params = useSearchParams();

  // URL is the single source of filter state (deep links from the overview
  // attention feed arrive as /reviews?rating=1, /reviews?status=escalated).
  const tab = (params.get("status") as StatusTab) || "all";
  const tone = (params.get("tone") as ReviewTone) || undefined;
  const period = (params.get("period") as ReviewPeriod) || undefined;
  const platform = (params.get("platform") as ReviewPlatform) || undefined;
  const organizationId = params.get("organization_id") ?? undefined;
  const paidOnly = params.get("is_paid") === "true" || undefined;
  const aspect = params.get("aspect") ?? undefined;
  const sort = (params.get("sort") as ReviewSort) || "new";
  const rating = params.get("rating") ?? undefined;
  const newOnly = params.get("new_only") === "true" || undefined;

  const [reviews, setReviews] = useState<Review[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<ReviewsSummary | null>(null);
  const [aspects, setAspects] = useState<AspectsResponse | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const setParams = useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(params.toString());
      Object.entries(patch).forEach(([key, value]) => {
        if (value === undefined) next.delete(key);
        else next.set(key, value);
      });
      const qs = next.toString();
      router.replace(qs ? `/reviews?${qs}` : "/reviews");
    },
    [params, router],
  );

  const feedParams = useCallback(
    (offset: number) => ({
      status: tab === "all" ? undefined : tab,
      tone,
      period,
      platform,
      organization_id: organizationId,
      is_paid: paidOnly,
      aspect,
      sort,
      rating,
      new_only: newOnly,
      limit: PAGE_SIZE,
      offset,
    }),
    [tab, tone, period, platform, organizationId, paidOnly, aspect, sort, rating, newOnly],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      listReviews(feedParams(0)),
      getReviewsSummary({
        tone, period, platform, organization_id: organizationId, is_paid: paidOnly, aspect, rating,
      }),
      getReviewAspects({ period: period ?? "30d", organization_id: organizationId, platform, aspect }),
      listOrganizations(),
    ])
      .then(([feed, sum, asp, organizations]) => {
        if (cancelled) return;
        setReviews(feed.items);
        setTotal(feed.total);
        setSummary(sum);
        setAspects(asp);
        setOrgs(organizations);
      })
      .catch(console.error)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [feedParams, tone, period, platform, organizationId, paidOnly, aspect, rating]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const feed = await listReviews(feedParams(reviews.length));
      setReviews((prev) => [...prev, ...feed.items]);
      setTotal(feed.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMore(false);
    }
  }

  function onFilterChange(patch: FeedFilterState) {
    setParams({
      tone: "tone" in patch ? patch.tone : tone,
      period: "period" in patch ? patch.period : period,
      platform: "platform" in patch ? patch.platform : platform,
      organization_id: "organizationId" in patch ? patch.organizationId : organizationId,
      is_paid: "paidOnly" in patch ? (patch.paidOnly ? "true" : undefined) : paidOnly ? "true" : undefined,
    });
  }

  function onPatched(updated: Review) {
    setReviews((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  const subtitle = summary
    ? `${summary.total} отзывов · ${summary.new_count} новых · ${summary.unanswered} без ответа · ${summary.overdue_24h} просрочены > 24ч`
    : "";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Отзывы</h1>
        {subtitle && <p className="mt-1 text-[13px] text-text-faint">{subtitle}</p>}
      </div>

      <StatusTabs tab={tab} summary={summary} onTab={(t) => setParams({ status: t === "all" ? undefined : t })} />

      <ReviewFilters
        tone={tone}
        period={period}
        platform={platform}
        organizationId={organizationId}
        paidOnly={paidOnly}
        orgs={orgs}
        summary={summary}
        onChange={onFilterChange}
        onReset={() => router.replace("/reviews")}
      />

      <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[14px] font-semibold">Лента отзывов</div>
              <div className="text-[11.5px] text-text-faint">
                {sort === "new" ? "Хронологически · самые новые сверху" : "Критичные сверху"}
              </div>
            </div>
            <div className="flex gap-1 rounded-lg border border-border bg-surface-2 p-0.5 text-[12px]">
              <button
                type="button"
                onClick={() => setParams({ sort: undefined })}
                className={`rounded px-2.5 py-1 ${sort === "new" ? "bg-surface-3 text-text" : "text-text-dim"}`}
              >
                ↻ Новые
              </button>
              <button
                type="button"
                onClick={() => setParams({ sort: "criticality" })}
                className={`rounded px-2.5 py-1 ${sort === "criticality" ? "bg-surface-3 text-text" : "text-text-dim"}`}
              >
                ⚡ По критичности
              </button>
            </div>
          </div>

          {loading ? (
            <div className="py-20 text-center text-text-faint">Загрузка…</div>
          ) : reviews.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface-1 py-14 text-center">
              <div className="text-3xl">📭</div>
              <div className="mt-2 font-semibold">Под выбранные фильтры ничего не нашлось</div>
              <div className="mt-1 text-[12.5px] text-text-faint">
                Попробуйте сбросить часть фильтров или расширить период.
              </div>
              <button
                type="button"
                onClick={() => router.replace("/reviews")}
                className="mt-4 rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[12.5px] text-text-dim hover:text-text"
              >
                Сбросить фильтры
              </button>
            </div>
          ) : (
            <>
              {reviews.map((review) => (
                <ReviewCard
                  key={review.id}
                  review={review}
                  onPatched={onPatched}
                  onAspect={(category) => setParams({ aspect: category })}
                />
              ))}
              {reviews.length < total && (
                <button
                  type="button"
                  disabled={loadingMore}
                  onClick={loadMore}
                  className="w-full rounded-xl border border-border bg-surface-1 py-2.5 text-[13px] text-text-dim hover:text-text disabled:opacity-50"
                >
                  {loadingMore ? "Загрузка…" : `Показать ещё (${total - reviews.length})`}
                </button>
              )}
            </>
          )}
        </div>

        <AspectsPanel
          data={aspects}
          activeAspect={aspect ?? null}
          onAspect={(category) => setParams({ aspect: category ?? undefined })}
        />
      </div>
    </div>
  );
}

export default function ReviewsPage() {
  return (
    <Suspense fallback={<div className="py-20 text-center text-text-faint">Загрузка…</div>}>
      <ReviewsContent />
    </Suspense>
  );
}
```

Note: `components/reviews-table.tsx` stays — the organization detail page still uses it.

- [ ] **Step 2: Verify compile + lint**

Run: `npx tsc --noEmit && npm run lint`
Expected: clean. Fix any `react-hooks/exhaustive-deps` warnings by following the lint suggestion (the effect deliberately depends on `feedParams` which already encodes all filters).

- [ ] **Step 3: Manual smoke (stack running)**

With API + web running (`docker compose up` or bare stack per local dev memory): open `/reviews`, check tabs/chips update the URL and the feed, aspect row click filters the feed, status buttons work when logged in as admin, `/reviews?status=escalated` and `/reviews?rating=1` deep links open pre-filtered.

- [ ] **Step 4: Commit**

```bash
git add "apps/web/app/(dashboard)/reviews/page.tsx"
git commit -m "feat(web): rebuild /reviews page per GeoMonitor prototype"
```

---

### Task 10: E2E + verification gate

**Files:**
- Create: `apps/web/tests/reviews.spec.ts`

**Interfaces:**
- Consumes: the finished page; same env gating as `apps/web/tests/overview.spec.ts` (`E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD`).

- [ ] **Step 1: Write the spec**

Create `apps/web/tests/reviews.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

// Reviews page rebuild (GeoMonitor prototype). Auth-gated like the rest of the panel.

test("unauthenticated reviews redirects to login", async ({ page }) => {
  await page.goto("/reviews");
  await expect(page).toHaveURL(/\/login$/);
});

const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("reviews page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
  }

  test("renders tabs, filters and aspects panel", async ({ page }) => {
    await login(page);
    await page.goto("/reviews");

    await expect(page.getByRole("heading", { name: "Отзывы" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Не отвечено/ })).toBeVisible();
    await expect(page.getByText("Аспектный анализ")).toBeVisible();
    await expect(page.getByText("Лента отзывов")).toBeVisible();
  });

  test("status tab updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/reviews");
    await page.getByRole("button", { name: /Не отвечено/ }).click();
    await expect(page).toHaveURL(/status=unanswered/);
  });

  test("period chip updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/reviews");
    await page.getByRole("button", { name: "7д", exact: true }).click();
    await expect(page).toHaveURL(/period=7d/);
  });

  test("escalated deep link opens pre-filtered", async ({ page }) => {
    await login(page);
    await page.goto("/reviews?status=escalated");
    await expect(page.getByRole("button", { name: /Эскалированные/ })).toHaveClass(/border-accent/);
  });
});
```

- [ ] **Step 2: Run the headless smokes**

Run (from `apps/web`): `npm run test:e2e -- reviews.spec.ts`
Expected: unauthenticated redirect test PASSES; authed suite SKIPS without env creds (or PASSES against a live stack with them set).

- [ ] **Step 3: Full verification gate**

```bash
cd apps/api && pytest -v
cd apps/web && npm run lint && npx tsc --noEmit
```
Expected: everything green.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/reviews.spec.ts
git commit -m "test(web): e2e smokes for rebuilt reviews page"
```
