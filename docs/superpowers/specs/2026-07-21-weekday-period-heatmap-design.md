# Weekday × date-period heatmap for the "Оценки по дням недели" block

**Date:** 2026-07-21
**Page:** `/ratings` — `weekday` block (feature 014)
**Status:** approved design

## Goal

Give the "Оценки по дням недели" block the prototype's heatmap look
(`docs/plans/dashboard_new/GeoMonitor — SERM Dashboard Prototype.html`),
adapted to the data we actually have.

## Hard constraint (why the prototype can't be copied literally)

The prototype's columns are **time-of-day** (00–04 … 20–24). We do not store
posting time: `Review.review_date` is a plain `Date` (no time component) and
`Review.first_seen_at` is scrape time, not publication time. Feature 014
deliberately reduced the prototype's 7×6 heatmap to a Mon–Sun bar chart for
this exact reason, and CLAUDE.md marks "no hour-of-day axis" as a hard rule.

The adaptation keeps the heatmap **grid look** but makes the columns something
real: **periods of the selected date range**.

## Behavior

- **Grid mode** is used **only** when `period=custom` with a valid
  `date_from`/`date_to` pair. Every other case (presets, all-time) keeps the
  existing Mon–Sun bar chart unchanged.
- **Rows** = weekday Пн…Вс (7).
- **Columns** = date-periods of the selected range, bucketed **adaptively** by
  the inclusive range length in days:
  - ≤ 14 days → **by day**
  - ≤ 92 days (~3 months) → **by ISO week**
  - otherwise → **by month**
- **Cell** encodes two dimensions, matching the prototype:
  - **hue** = average rating, via the existing thresholds
    (`≤ 4.0` red / `4.0–4.5` amber / `≥ 4.5` lime — `ratingColor`).
  - **intensity** = review count, opacity scaled by the count relative to the
    grid's max cell ("чем темнее ячейка — тем больше отзывов").
  - a weekday×period cell with **no** reviews → faint neutral, never invented
    data, `avg_rating = null`.

## Backend — `apps/api/app/services/dashboard_service.py`

`_weekday_stats` already receives `cutoff` and `until`. When **both** bounds are
present it additionally builds a **grid** with **one** grouped query:

```
GROUP BY (weekday_expr(review_date), bucket_key)
  -> count(), avg(rating)
```

- `weekday_expr` — existing `_weekday_expr` (dialect-safe, 0=Mon..6=Sun).
- `bucket_key` per granularity, reusing existing dialect-safe helpers:
  - day → `Review.review_date` directly
  - week → `_week_key_expr(review_date)`
  - month → `_month_key_expr(review_date)`
- Result is ≤ 7 × (number of columns) rows — bounded. In custom mode this query
  **replaces** the current single weekday query (does not add a query), so
  `test_query_counts.py` still holds; bars mode is byte-for-byte unchanged.
- Column list and labels are built in Python from the granularity + range
  (e.g. `"1–7 июл"`, `"нед. 27"`, `"Июл"`), so columns with zero reviews still
  appear as empty cells rather than being dropped.
- Insight: a short grid-oriented sentence (busiest / worst period-weekday) or a
  reuse of the existing weekday insight; `null` when there is nothing to
  compare.

## Schema — `apps/api/app/schemas/dashboard.py`

`WeekdayBlock` gains an optional field:

```python
class WeekdayGridCell(BaseModel):
    count: int
    avg_rating: float | None   # null = нет данных, never rendered as 0

class WeekdayGridRow(BaseModel):
    weekday: int
    label: str
    cells: list[WeekdayGridCell]  # aligned to columns

class WeekdayGridColumn(BaseModel):
    key: str
    label: str

class WeekdayGrid(BaseModel):
    columns: list[WeekdayGridColumn]
    rows: list[WeekdayGridRow]
    insight: str | None

class WeekdayBlock(BaseModel):
    days: list[WeekdayStat]      # unchanged, used by bar fallback
    insight: str | None          # unchanged
    grid: WeekdayGrid | None = None   # present only in custom mode
```

`WeekdayStat.count == 0` stays a real measurement; `avg_rating == null`
everywhere else means «нет данных».

## Frontend — `apps/web/components/dashboard/ratings/weekday-breakdown.tsx`

- If `block.grid` is present → render the heatmap table: weekday labels down the
  left, period labels across the top, colored cells. Cell background =
  `ratingColor(avg_rating)` with opacity scaled by `count / gridMax`; empty
  cells faint neutral. Count shown in-cell or on hover; `avg_rating` on hover.
- Else → the existing Mon–Sun bars (no change).
- Reuse the file's existing `ratingColor` + `LEGEND`.
- Wrap the grid in a horizontal-scroll container for many columns.
- `lib/types.ts` mirrors the new `WeekdayGrid`/`grid` shape.

## Tests — `apps/api/tests/test_dashboard_ratings.py`

- Custom range → grid present with the expected bucket granularity at each
  threshold (day ≤14, week ≤92, month otherwise).
- Preset period → `grid is None`, bars unchanged.
- Empty weekday×period cell → `avg_rating is None` (not 0).
- Query-count contract (`test_query_counts.py`) unchanged for both modes.

## Out of scope

- No hour-of-day axis (data does not exist).
- No new migration, no new dependency (hand-rolled SVG/CSS grid, consistent with
  the rest of `components/dashboard/ratings/`).
