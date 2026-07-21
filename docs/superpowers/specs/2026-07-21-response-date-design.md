# Design: Scraped Business-Response Date (`response_date`)

**Date:** 2026-07-21
**Status:** Approved — ready for implementation plan

## Problem

When we scrape a business reply to a review, we store only its text (`response_text`)
and the scrape-time proxy `response_first_seen_at` (feature 007 — *when our scraper
first saw* the reply, not when it was actually posted). Both Yandex and 2GIS expose the
**real publication date of the reply** in their JSON payloads. We currently discard it.
Operators need the platform's own response date (e.g. to reason about answer speed and
to display it next to the reply).

## Goal

Parse the real business-response date from both sources, normalize it to a Moscow-time
calendar day, persist it on the review, expose it through the API, and show it in the
review card.

Explicitly out of scope: response-speed / SLA analytics recomputation, backfill of
existing rows, changing `response_first_seen_at` semantics.

## Decisions (settled during brainstorming)

- **Granularity:** store a **day** (`Date`), consistent with `review_date`. Both sources
  give a precise timestamp; we resolve it to the MSK calendar day and drop the time.
- **Scope:** full cycle — scrape → DB → API schema → review card.
- **Edit behavior:** **sync** `response_date` on every scrape that carries a reply, so an
  edited reply (whose platform date moved) is reflected. Mirrors how `response_text` is
  already refreshed on update.

## Data model

New additive column on `reviews`:

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `response_date` | `Date` | YES | none | MSK calendar day the business reply was published on the platform. NULL when there is no reply, or the source carried no parseable date. **Never feeds `build_review_hash`.** |

Relationship to existing columns:
- `response_first_seen_at` (feature 007): our observation time — unchanged, kept as a
  secondary/fallback signal in the UI.
- `response_text`: reply text — unchanged. `response_date` tracks it (set/refreshed
  together).
- `content_hash`: dedup identity — `response_date` stays **excluded**, same as
  `response_text`/`response_first_seen_at`.

`ParsedReview` (`scraper/types.py`) gains `response_date: date | None = None`.

Migration `alembic/versions/0022_response_date.py`, `down_revision = "0021_session_login_progress"`:
- upgrade: `add_column("reviews", Column("response_date", Date, nullable=True))`
- downgrade: `drop_column("reviews", "response_date")`
- No data backfill (pre-feature rows stay NULL).

## Parsing — where the date lives in the markup

### Yandex (`scraper/parser.py`)
The reply and its date live only in the embedded SPA state JSON at
`reviewResults.reviews[].businessComment`:
```json
"businessComment": { "text": "…", "updatedTime": "2026-02-16T05:34:51.427Z" }
```
- `_business_comments_from_state` currently returns `{author, text, comment}`. Add
  `comment_date` = `iso_datetime_to_local_date(businessComment["updatedTime"])`.
- `_match_state_comment` currently returns the comment string. Change it to return the
  matched entry (comment text **and** date) so the caller can set both.
- The legacy DOM-bubble path (`.business-review-comment-content__bubble`, used by older
  fixtures) carries no reliable date node → `response_date` stays `None` there. Live
  pages always go through the state-JSON path, which has the date.

### 2GIS (`scraper/twogis_api.py::_map_review`)
The official reply is `official_answer` (dict). Its date field (`date_created`, with
`date_edited` as fallback) is read with the same normalization already used for
`review_date`:
```python
official = raw.get("official_answer")
if isinstance(official, dict):
    response_text = official.get("text")
    raw_date = official.get("date_created") or official.get("date_edited")
    response_date = (
        iso_datetime_to_local_date(raw_date)
        or normalize_review_date(raw_date[:10] if raw_date else None)
    )
```
Exact field name confirmed against a live API response during implementation.

## Persistence (`services/review_service.py`)

- **Insert** (`upsert_reviews`): set `response_date=parsed.response_date` on the new
  `Review` (meaningful only when `response_text` is present).
- **Update** (`_apply_update`): whenever the parsed review carries `response_text`, set
  `existing.response_date = parsed.response_date` — synced alongside the existing
  `response_text` refresh. `response_first_seen_at` remains set-once.

`response_date` is computed **outside** `build_review_hash` and passed as a plain field —
it cannot affect dedup.

## API + Frontend

- `schemas/review.py::ReviewResponse` gains `response_date: date | None = None`
  (populated via `from_attributes`). No new endpoint.
- `apps/web/lib/types.ts::Review` gains `response_date: string | null`.
- `apps/web/components/reviews/review-card.tsx`: in the "↪ Ответ компании" header, show
  the real date when present (`ответ от DD.MM.YYYY`); fall back to the existing
  `замечен {relTime(response_first_seen_at)}` when `response_date` is null.

## Tests (constitution critical-path: scrape-result persistence + dedup contract)

- `test_yandex_parser.py`: a `businessComment.updatedTime` yields the expected MSK
  `response_date` on the parsed review; DOM-only fixture leaves it `None`.
- `test_twogis_api.py`: `official_answer.date_created` yields the expected `response_date`;
  a missing/None `official_answer` leaves it `None`.
- `review_service` upsert: `response_date` is written on insert and when a reply first
  appears; an edited reply updates it; **`content_hash` is unchanged** when only the
  response date differs (dedup regression guard).

## Non-goals / risks

- No SLA/response-speed recomputation — additive field only.
- 2GIS `official_answer` date field name is verified against live data before shipping;
  the `iso_datetime_to_local_date` → `normalize_review_date` fallback makes an unexpected
  format degrade to `None` rather than raise.
