# Data Model: Dashboard Overview Performance

**Feature**: 012-dashboard-overview-perf · **Date**: 2026-07-19

No new entities, no column changes, no dedup-contract impact. Changes are additive indexes plus a fixed set of read-only query shapes.

## Entities (unchanged)

- **Review** — aggregation source. Columns consumed: `organization_id`, `platform`, `rating`, `first_seen_at`, `response_text` (NULL-check only), `response_first_seen_at`, `sentiment`, `problems`, `review_date`, `status`. `review_text` is **never** loaded by the overview anymore.
- **Organization** — filter scope + per-platform rating/count columns. Unchanged; still loaded fully (tens of rows).
- **RatingSnapshot** — unchanged; already batched via `_earliest_snapshot_ratings`.
- **AttentionRule** — unchanged; count-type rules now drive scoped COUNT queries instead of in-memory filters.

## Index additions (Alembic migration 0017, additive)

| Index | Definition | Serves |
|---|---|---|
| `ix_reviews_org_unanswered` | `(organization_id)` partial `WHERE response_text IS NULL` | A4 per-org unanswered counts, header/kpi unanswered counters, unanswered-overdue rules |
| `ix_reviews_org_platform_first_seen` | `(organization_id, platform, first_seen_at)` | platform-filtered period scans (A1–A3, A5, R1) |

Declared in `Review.__table_args__` with `postgresql_where` and `sqlite_where` so the pytest `create_all` schema matches production. Existing feature-010 indexes are kept as-is.

## Query shapes (read-only; the service's new data access contract)

Scope filters applied to every query: `organization_id IN (selected)`, plus `platform = X` when the page filter isn't `all`. `cutoff` = period start (aware UTC; naive-UTC bind on SQLite — research R2).

| ID | Result shape | Notes |
|---|---|---|
| A1 | 1 row: `{total, new_in_period, new_today, fresh_neg_2h, unanswered_total, unanswered_overdue_24h, unanswered_new_24h, min_first_seen}` | `COUNT(*) FILTER (...)` per counter; SQLite ≥3.30 supports FILTER (stdlib sqlite3 on CI/dev OK) — else `SUM(CASE WHEN ...)` fallback via SQLAlchemy `case()` (portable, chosen form) |
| A2 | rows `(rating, count)` | period rows, `WHERE rating IS NOT NULL GROUP BY rating` |
| A3 | rows `(sentiment, count)` | period rows, `GROUP BY sentiment` incl. NULL bucket; NULL row excluded from `analyzed_total` |
| A4 | rows `(organization_id, count)` | `WHERE response_text IS NULL GROUP BY organization_id` (all-time, matching current `_worst_locations`) |
| A5 | rows `(platform, rated_count, negative_count, response_sum_seconds, response_count)` | period rows, platform-agnostic (ignores page platform filter, as today); Python computes negativity % and avg hours |
| R1 | tuples `(first_seen_at, response_first_seen_at)` | period rows `WHERE response_first_seen_at IS NOT NULL`; Python median/p95 |
| R2 | tuples `(organization_id, review_date, problems, sentiment)` | `WHERE review_date >= now-14d AND problems IS NOT NULL`; feeds `_trending_aspects` + `_aspect_spikes` |
| A6× | 1 scalar per count-type enabled rule | params from `rule.params`; same scope semantics as current in-memory filter |

**Invariant**: SQL returns raw counts/sums; all rounding (`round()`), percentages, sorting, tie-breaking, and top-N slicing remain in existing Python code (research R7).

## Behavioral invariants (contract with tests)

- `removed_at` is **ignored** by overview aggregation (current behavior — removed rows are included), preserved as-is.
- `sentiment` NULL rows: excluded from `analyzed_total` and all sentiment buckets (matches `summarize`).
- `rating` NULL rows: excluded from rating distribution and reputation math (SQLite test rows always have ratings; PG column is NOT NULL — filter kept for parity with current list comprehension).
- Window boundaries use the same operators as current Python: `first_seen_at >= cutoff`, `>= today_start`, `>= cutoff_24h`, `<= cutoff_24h`, `>= cutoff_2h`.
