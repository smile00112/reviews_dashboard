# Weekday × date-period heatmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `/ratings`, render the "Оценки по дням недели" block as a weekday × date-period heatmap (prototype look) when a custom date range is selected, keeping today's Mon–Sun bars for every other period.

**Architecture:** Backend `_weekday_stats` gains a grid branch that fires only when both range bounds are present (`cutoff` and `until`) — the unique signature of `period=custom` in this codebase. It runs one extra `GROUP BY (weekday, bucket_key)` query, bucketing `review_date` adaptively (day ≤14d / ISO week ≤92d / month otherwise) via existing dialect-safe helpers. The grid is an optional field on `WeekdayBlock`; the web component renders the heatmap when `grid` is present, else the existing bars.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite in tests, Postgres in prod), Pydantic, Next.js App Router (server component page + client-safe presentational component), hand-rolled CSS grid (no new deps).

## Global Constraints

- `null`/`None` means «нет данных» and is NEVER rendered as `0`. Sole exception: `WeekdayStat.count`, where `0` is a real measurement (its `avg_rating` is then `null`). Copied verbatim from spec.
- No new migration, no new dependency. Charts are hand-rolled SVG/CSS under `components/dashboard/ratings/`.
- No hour-of-day axis — posting time is not stored (`review_date` is a `Date`; `first_seen_at` is scrape time).
- `test_query_counts.py` must pass unmodified: the SELECT count must scale with neither org nor review volume. In custom mode the grid query **replaces** the current weekday query (net query count unchanged); bars mode stays byte-for-byte identical.
- `test_dashboard_ratings.py` is the contract — extend it, do not weaken existing assertions.
- Grid mode fires only when `period=custom` with a valid ordered `date_from`/`date_to`. In this codebase that is exactly `cutoff is not None and until is not None` (presets never set `until`).
- Adaptive bucket thresholds (inclusive range length in days): `≤ 14` → day, `≤ 92` → ISO week, else → month.

---

### Task 1: Backend grid computation in `_weekday_stats`

**Files:**
- Modify: `apps/api/app/services/dashboard_service.py` (`_weekday_stats` ~1559-1605; add helpers near it)
- Test: `apps/api/tests/test_dashboard_ratings.py`

**Interfaces:**
- Consumes: `self._weekday_expr(col)`, `self._week_key_expr(col)`, `self._month_key_expr(col)`, `self._published_expr()`, `self._scoped_filters(org_ids, platform)`, `self._empty_weekdays()`, module constants `_WEEKDAY_LABELS` (7 items, `["Пн"..."Вс"]`), `_WEEKDAY_FULL`.
- Produces: `_weekday_stats(...)` return dict now optionally contains key `"grid"`. Grid shape (plain dicts, mirrored by the Pydantic models in Task 2):
  - `grid = {"columns": [{"key": str, "label": str}, ...], "rows": [{"weekday": int, "label": str, "cells": [{"count": int, "avg_rating": float | None}, ...]}, ...], "insight": str | None}` — 7 rows, each `cells` list index-aligned to `columns`.
  - When not custom mode, `"grid"` key is **absent** (or `None`).
- New private helpers produced for later reuse within this file only:
  - `_weekday_grid_granularity(cutoff: datetime, until: date) -> str` → returns `"day" | "week" | "month"`.
  - `_weekday_grid_columns(gran: str, start: date, end: date) -> list[dict]` → ordered `[{"key","label"}]` covering the whole range (including empty periods).
  - `_weekday_grid_bucket_expr(gran)` → SQLAlchemy expression matching the column `key`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/test_dashboard_ratings.py`. Reuse the module's existing fixtures/helpers for seeding an org + reviews with explicit `review_date` values and calling `DashboardService(session).ratings(...)`. If a helper to create a review with a given date/rating/platform already exists in this test module, use it; otherwise add a small local helper mirroring the existing seeding style in this file.

```python
def test_weekday_grid_present_only_for_custom_range(dashboard_session):
    # Seed a handful of yandex reviews across two dates/weekdays.
    _seed_reviews(dashboard_session, dates_ratings=[
        (date(2026, 6, 1), 5),   # Monday
        (date(2026, 6, 2), 3),   # Tuesday
        (date(2026, 6, 8), 4),   # Monday
    ])
    svc = DashboardService(dashboard_session)

    preset = svc.ratings(period="30d", platform="all")
    assert preset["weekday"].get("grid") is None  # bars mode only

    custom = svc.ratings(
        period="custom", platform="all",
        date_from=date(2026, 6, 1), date_to=date(2026, 6, 14),
    )
    grid = custom["weekday"]["grid"]
    assert grid is not None
    assert len(grid["rows"]) == 7
    # 14-day range -> daily buckets
    assert len(grid["columns"]) == 14
    for row in grid["rows"]:
        assert len(row["cells"]) == len(grid["columns"])


def test_weekday_grid_granularity_thresholds(dashboard_session):
    _seed_reviews(dashboard_session, dates_ratings=[(date(2026, 1, 5), 5)])
    svc = DashboardService(dashboard_session)

    day = svc.ratings(period="custom", platform="all",
                      date_from=date(2026, 1, 1), date_to=date(2026, 1, 14))
    assert len(day["weekday"]["grid"]["columns"]) == 14  # daily

    week = svc.ratings(period="custom", platform="all",
                       date_from=date(2026, 1, 1), date_to=date(2026, 3, 1))
    # ~60 days -> weekly buckets, far fewer than 60 columns
    assert 0 < len(week["weekday"]["grid"]["columns"]) <= 10

    month = svc.ratings(period="custom", platform="all",
                        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
    # 365 days -> monthly buckets
    assert len(month["weekday"]["grid"]["columns"]) == 12


def test_weekday_grid_empty_cell_avg_is_null(dashboard_session):
    # Single review on Monday 2026-06-01; every other weekday/period empty.
    _seed_reviews(dashboard_session, dates_ratings=[(date(2026, 6, 1), 5)])
    svc = DashboardService(dashboard_session)
    grid = svc.ratings(period="custom", platform="all",
                       date_from=date(2026, 6, 1), date_to=date(2026, 6, 14))["weekday"]["grid"]
    # Find a cell with count 0 -> avg_rating must be None, never 0.
    empties = [c for row in grid["rows"] for c in row["cells"] if c["count"] == 0]
    assert empties, "expected empty cells in a sparse grid"
    assert all(c["avg_rating"] is None for c in empties)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_dashboard_ratings.py -k "weekday_grid" -v`
Expected: FAIL (`grid` key missing / KeyError or `.get("grid") is None` passing but the custom assertions failing on `None`).

- [ ] **Step 3: Add the granularity + column helpers**

In `apps/api/app/services/dashboard_service.py`, near `_weekday_stats`, add:

```python
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

    @classmethod
    def _weekday_grid_columns(cls, gran: str, start: date, end: date) -> list[dict]:
        cols: list[dict] = []
        if gran == "day":
            cur = start
            while cur <= end:
                cols.append({
                    "key": cur.isoformat(),
                    "label": f"{cur.day} {cls._RU_MONTHS_SHORT[cur.month - 1]}",
                })
                cur += timedelta(days=1)
        elif gran == "week":
            # Bucket by ISO week; walk week-by-week from the Monday of `start`.
            cur = start - timedelta(days=start.weekday())
            while cur <= end:
                iso_year, iso_week, _ = cur.isocalendar()
                cols.append({
                    "key": f"{iso_year:04d}-W{iso_week:02d}",
                    "label": f"нед. {iso_week}",
                })
                cur += timedelta(days=7)
        else:  # month
            y, m = start.year, start.month
            while (y, m) <= (end.year, end.month):
                cols.append({
                    "key": f"{y:04d}-{m:02d}",
                    "label": cls._RU_MONTHS_SHORT[m - 1].capitalize(),
                })
                m += 1
                if m > 12:
                    m, y = 1, y + 1
        return cols

    def _weekday_grid_bucket_expr(self, gran: str):
        if gran == "day":
            # `key` compared as ISO date string, matching column keys.
            if self.db.get_bind().dialect.name == "sqlite":
                return func.strftime("%Y-%m-%d", Review.review_date)
            return func.to_char(Review.review_date, "YYYY-MM-DD")
        if gran == "week":
            return self._week_key_expr(Review.review_date)
        return self._month_key_expr(Review.review_date)
```

Confirm `timedelta` and `date` are imported at the top of the file (they are used elsewhere; add to the existing `from datetime import ...` line if missing).

Note on week keys: `_week_key_expr` on SQLite emits `%Y-W%W`; the Python column keys must match its formatting. Use the same helper by formatting the column key from a probe: instead of hand-building `f"{iso_year}-W{iso_week:02d}"`, derive week keys from the DB helper by grouping (see Step 4) — but for the *column list* we still need deterministic ordering. To keep keys identical across Python and SQL, in Step 4 build the column list from the **distinct bucket keys actually returned by the query, unioned with** a generated ordered skeleton, and sort by the underlying date. Implement the skeleton with a representative date per bucket and format its key via a single shared function `_bucket_key_for_date(gran, d)`:

```python
    def _bucket_key_for_date(self, gran: str, d: date) -> str:
        if gran == "day":
            return d.isoformat()
        if gran == "week":
            iso_year, iso_week, _ = d.isocalendar()
            # Mirror _week_key_expr: PG uses ISO week; SQLite uses %W.
            if self.db.get_bind().dialect.name == "sqlite":
                return d.strftime("%Y-W%W")
            return f"{iso_year:04d}-W{iso_week:02d}"
        return f"{d.year:04d}-{d.month:02d}"
```

Then rewrite `_weekday_grid_columns` to build `key` via `self._bucket_key_for_date(gran, representative_date)` so Python keys and SQL group keys are guaranteed identical on both dialects.

- [ ] **Step 4: Add the grid branch to `_weekday_stats`**

Change `_weekday_stats` so that when both bounds are present it also builds the grid. Keep the existing bars computation and return exactly as before, only adding the `"grid"` key in custom mode:

```python
        result = {"days": days, "insight": self._weekday_insight(days)}

        if cutoff is not None and until is not None:
            result["grid"] = self._weekday_grid(scope_filters=filters, cutoff=cutoff, until=until)
        return result
```

Add the grid builder (uses the same `filters` already assembled in `_weekday_stats`, which include scope, `removed_at IS NULL`, `review_date IS NOT NULL`, and the published-range bounds):

```python
    def _weekday_grid(self, scope_filters: list, cutoff: datetime, until: date) -> dict:
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
            ci = col_index.get(str(r.bucket))
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
        return {"columns": columns, "rows": grid_rows, "insight": self._weekday_grid_insight(grid_rows)}

    @staticmethod
    def _weekday_grid_insight(grid_rows: list[dict]) -> str | None:
        rated = [
            (row["label"], c["avg_rating"])
            for row in grid_rows for c in row["cells"]
            if c["avg_rating"] is not None
        ]
        if len(rated) < 2:
            return None
        worst = min(rated, key=lambda t: t[1])
        best = max(rated, key=lambda t: t[1])
        if worst[1] == best[1]:
            return None
        return (
            f"Худшие оценки — {worst[0]} (средняя {worst[1]:.2f}). "
            f"Лучшие — {best[0]} ({best[1]:.2f})."
        )
```

`_empty_ratings_payload` is untouched (its `weekday` has no `grid` key → treated as bars, correct for the empty case).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_dashboard_ratings.py -k "weekday" -v`
Expected: PASS (both new grid tests and the pre-existing weekday tests).

- [ ] **Step 6: Run the query-count contract**

Run: `cd apps/api && pytest tests/test_query_counts.py -v`
Expected: PASS (grid query replaces the weekday query in custom mode; presets unchanged).

- [ ] **Step 7: Run the full ratings + query-count suites**

Run: `cd apps/api && pytest tests/test_dashboard_ratings.py tests/test_query_counts.py -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/dashboard_service.py apps/api/tests/test_dashboard_ratings.py
git commit -m "feat(ratings): compute weekday x date-period heatmap grid for custom ranges"
```

---

### Task 2: Pydantic + TypeScript schema for the grid

**Files:**
- Modify: `apps/api/app/schemas/dashboard.py` (add grid models; extend `WeekdayBlock` ~182-192)
- Modify: `apps/web/lib/types.ts` (add grid interfaces; extend `WeekdayBlock` ~356-367)
- Test: `apps/api/tests/test_dashboard_ratings.py` (serialization assertion)

**Interfaces:**
- Consumes: the `"grid"` dict shape produced by Task 1.
- Produces (Pydantic): `WeekdayGridColumn{key:str,label:str}`, `WeekdayGridCell{count:int,avg_rating:float|None}`, `WeekdayGridRow{weekday:int,label:str,cells:list[WeekdayGridCell]}`, `WeekdayGrid{columns:list[WeekdayGridColumn],rows:list[WeekdayGridRow],insight:str|None}`; `WeekdayBlock.grid: WeekdayGrid | None = None`.
- Produces (TS): matching `WeekdayGridColumn`, `WeekdayGridCell`, `WeekdayGridRow`, `WeekdayGrid`; `WeekdayBlock.grid: WeekdayGrid | null`.

- [ ] **Step 1: Write the failing serialization test**

Add to `apps/api/tests/test_dashboard_ratings.py`:

```python
def test_ratings_response_serializes_weekday_grid(dashboard_session):
    from app.schemas.dashboard import DashboardRatingsResponse  # actual response model name
    _seed_reviews(dashboard_session, dates_ratings=[(date(2026, 6, 1), 5)])
    payload = DashboardService(dashboard_session).ratings(
        period="custom", platform="all",
        date_from=date(2026, 6, 1), date_to=date(2026, 6, 14),
    )
    model = DashboardRatingsResponse.model_validate(payload)
    assert model.weekday.grid is not None
    assert len(model.weekday.grid.rows) == 7
    assert model.weekday.grid.columns[0].key
```

If the response wrapper class has a different name, grep `apps/api/app/schemas/dashboard.py` for the ratings response model and use that; if the endpoint validates via `WeekdayBlock` directly, validate `WeekdayBlock.model_validate(payload["weekday"])` instead.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && pytest tests/test_dashboard_ratings.py -k "serializes_weekday_grid" -v`
Expected: FAIL (`WeekdayBlock` has no `grid` attribute → validation ignores it / AttributeError on `.grid`).

- [ ] **Step 3: Add the Pydantic models**

In `apps/api/app/schemas/dashboard.py`, immediately before `class WeekdayBlock` (~189):

```python
class WeekdayGridColumn(BaseModel):
    key: str
    label: str


class WeekdayGridCell(BaseModel):
    count: int
    avg_rating: float | None  # None = нет данных (never 0)


class WeekdayGridRow(BaseModel):
    weekday: int  # 0 = Monday .. 6 = Sunday
    label: str
    cells: list[WeekdayGridCell]  # index-aligned with WeekdayGrid.columns


class WeekdayGrid(BaseModel):
    columns: list[WeekdayGridColumn]
    rows: list[WeekdayGridRow]
    insight: str | None
```

And extend `WeekdayBlock`:

```python
class WeekdayBlock(BaseModel):
    days: list[WeekdayStat]
    insight: str | None
    grid: WeekdayGrid | None = None  # present only for custom date ranges
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/api && pytest tests/test_dashboard_ratings.py -k "serializes_weekday_grid" -v`
Expected: PASS.

- [ ] **Step 5: Add the TypeScript interfaces**

In `apps/web/lib/types.ts`, before `interface WeekdayBlock` (~364):

```typescript
export interface WeekdayGridColumn {
  key: string;
  label: string;
}

export interface WeekdayGridCell {
  count: number;
  avg_rating: number | null; // null = нет данных, never rendered as 0
}

export interface WeekdayGridRow {
  /** 0 = Monday .. 6 = Sunday */
  weekday: number;
  label: string;
  /** index-aligned with WeekdayGrid.columns */
  cells: WeekdayGridCell[];
}

export interface WeekdayGrid {
  columns: WeekdayGridColumn[];
  rows: WeekdayGridRow[];
  insight: string | null;
}
```

And extend `WeekdayBlock`:

```typescript
export interface WeekdayBlock {
  days: WeekdayStat[];
  insight: string | null;
  grid?: WeekdayGrid | null;
}
```

- [ ] **Step 6: Typecheck the web types**

Run: `cd apps/web && npm run lint`
Expected: PASS (no type errors from the new interfaces).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/schemas/dashboard.py apps/web/lib/types.ts apps/api/tests/test_dashboard_ratings.py
git commit -m "feat(ratings): add weekday grid schema (api + web types)"
```

---

### Task 3: Render the heatmap in `weekday-breakdown.tsx`

**Files:**
- Modify: `apps/web/components/dashboard/ratings/weekday-breakdown.tsx`

**Interfaces:**
- Consumes: `WeekdayBlock.grid` (`WeekdayGrid`) from Task 2; existing local `ratingColor(rating)` and `LEGEND` in this file.
- Produces: no exports beyond the existing `WeekdayBreakdown`.

- [ ] **Step 1: Add the grid renderer and branch**

Replace the body of `WeekdayBreakdown` so it renders the heatmap when `block.grid` is present, else the existing bars. Add a `WeekdayHeatmap` helper component in the same file. Keep the `Panel` wrapper, title, legend, and empty-state style consistent with the current file.

```tsx
import type { WeekdayBlock, WeekdayGrid } from "@/lib/types";
import { Panel } from "../panel";

/** Colour by average rating, matching the prototype's heatmap legend. */
function ratingColor(rating: number): string {
  if (rating >= 4.5) return "#d4ff3a";
  if (rating >= 4.0) return "#fbbf24";
  return "#f87171";
}

const LEGEND = [
  { label: "≤ 4.0", color: "#f87171" },
  { label: "4.0–4.5", color: "#fbbf24" },
  { label: "≥ 4.5", color: "#d4ff3a" },
];

function WeekdayHeatmap({ grid }: { grid: WeekdayGrid }) {
  const maxCount = Math.max(
    1,
    ...grid.rows.flatMap((r) => r.cells.map((c) => c.count)),
  );

  return (
    <div className="overflow-x-auto">
      <div className="min-w-max">
        {/* Header row: blank corner + period labels */}
        <div
          className="grid gap-1.5"
          style={{
            gridTemplateColumns: `40px repeat(${grid.columns.length}, minmax(56px, 1fr))`,
          }}
        >
          <div />
          {grid.columns.map((col) => (
            <div
              key={col.key}
              className="pb-1 text-center font-mono text-[11px] uppercase text-text-faint"
            >
              {col.label}
            </div>
          ))}
        </div>

        {/* One grid row per weekday */}
        {grid.rows.map((row) => (
          <div
            key={row.weekday}
            className="mb-1.5 grid items-center gap-1.5"
            style={{
              gridTemplateColumns: `40px repeat(${grid.columns.length}, minmax(56px, 1fr))`,
            }}
          >
            <div className="font-mono text-xs font-semibold uppercase text-text-faint">
              {row.label}
            </div>
            {row.cells.map((cell, i) => {
              const empty = cell.avg_rating === null;
              // Intensity by volume: darker/stronger = more reviews.
              const intensity = empty ? 0 : 0.2 + 0.8 * (cell.count / maxCount);
              return (
                <div
                  key={grid.columns[i].key}
                  className="flex h-[34px] items-center justify-center rounded text-xs font-semibold"
                  title={
                    empty
                      ? "нет отзывов"
                      : `${row.label} · ${grid.columns[i].label}: ${cell.count.toLocaleString(
                          "ru-RU",
                        )} отз., ${cell.avg_rating!.toFixed(2)} ★`
                  }
                  style={{
                    background: empty ? "#1c2130" : ratingColor(cell.avg_rating!),
                    opacity: empty ? 0.4 : intensity,
                    color: empty ? "#4b5163" : "#0b0e14",
                  }}
                >
                  {empty ? "" : cell.avg_rating!.toFixed(1)}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Review volume and average rating per weekday.
 *
 * With a custom date range the block becomes a weekday x date-period heatmap
 * (prototype look); otherwise it stays a Mon-Sun bar chart. Reviews carry only
 * a calendar date (no posting time), so there is deliberately no hour-of-day
 * axis — the columns are periods of the selected range instead.
 */
export function WeekdayBreakdown({ block }: { block: WeekdayBlock }) {
  const grid = block.grid ?? null;
  const max = Math.max(1, ...block.days.map((d) => d.count));
  const hasBars = block.days.some((d) => d.count > 0);
  const hasGrid = grid !== null && grid.rows.some((r) => r.cells.some((c) => c.count > 0));

  const meta = grid
    ? "Строки — дни недели · столбцы — периоды диапазона · цвет — средний рейтинг"
    : "Длина полосы — количество отзывов · цвет — средний рейтинг";

  return (
    <Panel
      title="Оценки по дням недели"
      meta={meta}
      action={
        <div className="flex flex-wrap gap-3.5 text-[11px] text-text-dim">
          {LEGEND.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: l.color }}
              />
              {l.label}
            </span>
          ))}
        </div>
      }
    >
      {grid ? (
        !hasGrid ? (
          <div className="py-10 text-center text-text-faint">
            Нет отзывов с датой за выбранный период
          </div>
        ) : (
          <>
            <WeekdayHeatmap grid={grid} />
            {grid.insight && (
              <div className="mt-4 rounded-lg border-l-[3px] border-accent bg-surface-2 px-3.5 py-3 text-[12.5px] text-text-dim">
                💡 {grid.insight}
              </div>
            )}
          </>
        )
      ) : !hasBars ? (
        <div className="py-10 text-center text-text-faint">
          Нет отзывов с датой за выбранный период
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-1.5 py-1.5">
            {block.days.map((day) => (
              <div
                key={day.weekday}
                className="grid grid-cols-[40px_1fr_120px] items-center gap-3"
              >
                <div className="font-mono text-xs font-semibold uppercase text-text-faint">
                  {day.label}
                </div>
                <div className="h-[26px] overflow-hidden rounded bg-surface-2">
                  <div
                    className="h-full rounded transition-[width] duration-500"
                    style={{
                      width: `${(day.count / max) * 100}%`,
                      background:
                        day.avg_rating === null ? "#2a3041" : ratingColor(day.avg_rating),
                      opacity: day.avg_rating === null ? 0.5 : 0.85,
                    }}
                  />
                </div>
                <div className="text-right font-mono text-xs">
                  <b className="font-semibold text-text">
                    {day.count.toLocaleString("ru-RU")}
                  </b>
                  <span className="ml-2 text-text-faint">
                    {day.avg_rating === null ? "—" : `${day.avg_rating.toFixed(2)} ★`}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {block.insight && (
            <div className="mt-4 rounded-lg border-l-[3px] border-accent bg-surface-2 px-3.5 py-3 text-[12.5px] text-text-dim">
              💡 {block.insight}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd apps/web && npm run lint`
Expected: PASS.

- [ ] **Step 3: Visual smoke check**

Start the stack (see `run-local-stack` skill / `docker compose up`) and open `http://localhost:3000/ratings`. Select period **«Произвольный»** with a from/to spanning ~2 weeks → the block shows a 7×14 heatmap. Widen to ~2 months → columns become weeks; ~1 year → months. Switch back to a preset (e.g. 30 дней) → the block reverts to the Mon–Sun bars. Confirm empty cells render faint with no number, and hover tooltips show count + rating.

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/dashboard/ratings/weekday-breakdown.tsx
git commit -m "feat(ratings): render weekday x date-period heatmap for custom ranges"
```

---

### Task 4: Final verification gate

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `cd apps/api && pytest -v`
Expected: PASS (all, including `test_dashboard_ratings.py` and `test_query_counts.py`).

- [ ] **Step 2: Web lint + E2E (if stack is up)**

Run: `cd apps/web && npm run lint && npm run test:e2e`
Expected: lint PASS; E2E PASS (or note if the local stack isn't running — E2E expects API + web up).

- [ ] **Step 3: Commit any fixes**

If verification surfaced issues, fix them within the relevant task's file and commit:

```bash
git add -A
git commit -m "fix(ratings): address weekday heatmap verification findings"
```

---

## Self-Review notes

- **Spec coverage:** grid-only-on-custom (Task 1 branch + Task 3 render gate), adaptive day/week/month thresholds (Task 1 `_weekday_grid_granularity`, tested), hue=rating + intensity=volume (Task 3 `WeekdayHeatmap`), empty cell = `null` never 0 (Task 1 + tests), one grouped query / query-count contract (Task 1 Step 6), bars unchanged for presets (Task 1 keeps `days`, Task 3 keeps bar branch), schema mirror api↔web (Task 2), no migration / no dep (nothing added). All covered.
- **Placeholder scan:** none — every code step shows full code; the only conditional lookups (test fixture helper name, response model class name) include the exact grep-and-substitute instruction.
- **Type consistency:** grid dict keys in Task 1 (`columns`/`rows`/`cells`/`count`/`avg_rating`/`weekday`/`label`/`key`) match the Pydantic and TS models in Task 2 and the component reads in Task 3. `WeekdayGrid` imported in Task 3 matches the Task 2 export.
