# Research: Dashboard Overview Performance

**Feature**: 012-dashboard-overview-perf · **Date**: 2026-07-19

## R1 — Where the 5 seconds go

**Finding**: `DashboardService.overview` calls `base.all()` (`dashboard_service.py:217`) — full ORM hydration of every review for the selected orgs, all time, including `review_text` (unbounded text) and `problems` (JSONB). Period filtering happens afterwards in Python (`:218`). `_platform_cards` re-queries **all** reviews a second time when `platform != "all"` (`:380`). Every block then loops the hydrated lists.

**Decision**: eliminate full hydration entirely; aggregates in SQL, per-review loads narrowed to needed columns + time windows (see plan Design table).

**Alternatives considered**:
- *Column-pruned single load (`with_entities`)*: 5–10× cheaper but still O(total reviews) per request and still Python loops — rejected as the end state (acceptable as intermediate step only).
- *Response cache (TTL)*: masks latency between refreshes, doesn't meet SC-003 (memory) or SC-001 on cold path — out of scope per spec assumption.

## R2 — Aware/naive datetime comparisons across PG and SQLite

**Finding**: `reviews.first_seen_at` / `response_first_seen_at` are `DateTime(timezone=True)`. On PostgreSQL these are `timestamptz` — aware binds compare correctly. On SQLite (test backend) datetimes are stored as ISO strings; rows written with aware datetimes carry `+00:00`, rows from `server_default=func.now()` are naive — the current code papers over this in Python via `_aware()` (naive ⇒ UTC). Moving comparisons into SQL makes them lexicographic string comparisons on SQLite, where an aware bind (`...+00:00`) vs a naive stored value (or vice versa) can misorder on shared prefixes.

**Decision**: single helper (e.g. `_dt_param(dt)`) that strips tzinfo (converting to UTC first) when the session dialect is `sqlite`, and passes the aware datetime through on `postgresql`. All cutoff binds go through it. Existing suites (`test_dashboard_overview.py` uses aware `NOW`, upsert-seeded rows use `func.now()`) act as the regression net.

**Alternatives considered**:
- *`julianday()` / dialect-specific SQL functions*: heavier, spreads dialect branching through every query — rejected.
- *Naive-everywhere storage change*: schema/data migration far out of scope — rejected.

## R3 — Reproducing `summarize()` percents from grouped counts

**Finding**: `_sentiment` and `_kpi_strip.positivity_percent` only consume `sentiment_distribution`, `sentiment_percent`, `analyzed_reviews` from `analysis.analyzer.summarize`. Formula: `pct = round(part / n * 100, 1)` with `n = count(sentiment IS NOT NULL)`; unknown sentiment labels are counted in `n` but in no bucket.

**Decision**: one `GROUP BY sentiment` query (A3); compute the same buckets/percents with the identical `round(part / n * 100, 1)` expression in the service. `summarize()` itself is untouched (still used by org-level analytics endpoints). Rows with sentiment values outside {positive,negative,neutral} contribute to `analyzed_total` only — matching current behavior exactly.

**Alternatives considered**: keep calling `summarize()` over narrow tuples — requires loading every period row's sentiment fields (O(period reviews) transfer) for what SQL counts in one pass — rejected.

## R4 — Attention rules without the in-memory review list

**Finding**: `_attention` filters the already-loaded `all_reviews` per rule scope; count-type rules (`unanswered_overdue`, `fresh_negative`, `escalated`) reduce to scoped COUNTs with per-rule params (hours/window/max_rating from `rule.params`, so counters cannot be precomputed once for all rules). `aspect_spike` needs 14-day problems rows; `rating_drop` needs only orgs + snapshots (already batched).

**Decision**: per enabled count-type rule, issue one scoped `COUNT` query (same org-scope + page platform filter as today). Query count grows with *enabled rule count* (operator-bounded, single digits), not with orgs or reviews — the existing `test_overview_query_count_does_not_scale_with_orgs` guard semantics are preserved. `aspect_spike` reuses the R2 narrow load; `rating_drop` unchanged.

**Alternatives considered**: one giant UNION query for all rules — unreadable, no measurable win at single-digit rule counts — rejected (YAGNI).

## R5 — Precomputed daily aggregate table ("history table")

**Finding** (user's original question): a per-org×platform×day aggregate table would speed period aggregation, but (a) real-time blocks (fresh negatives 2h, unanswered >24h, new today) still need live queries; (b) retroactive mutations (`response_text` filled on re-scrape, `removed_at` set/cleared) silently invalidate historical daily rows, requiring re-aggregation machinery; (c) `rating_snapshot` already covers the one genuinely historical need (rating deltas).

**Decision**: rejected for this feature (constitution Principle V). Indexed SQL aggregates meet the <300 ms target at 10× current volume without new tables, jobs, or invalidation logic. Revisit only if long-horizon history charts become a feature — then as an extension of `rating_snapshot`.

## R6 — Index support

**Finding**: existing indexes (feature 010): `(org, review_date)`, `(org, first_seen_at)`, `(org, platform)`. Missing for the new query set: unanswered lookups (`response_text IS NULL` predicate) and combined platform+time scans.

**Decision**: add partial index `(organization_id) WHERE response_text IS NULL` and composite `(organization_id, platform, first_seen_at)` in migration 0017; declare on the model with `postgresql_where`+`sqlite_where` so pytest's `create_all` schema stays equivalent. Verify with `EXPLAIN ANALYZE` in quickstart.

## R8 — Measured outcome and why the query set collapsed to one cube

**Finding** (post-implementation, real dataset: 604 organizations, 52,559 reviews): the per-block aggregate design of R1 worked but left ~700 ms on the table. Profiling attributed it to three things the plan had not anticipated: (a) the network is 604 organizations, not "tens", so every `organization_id IN (…)` bind list was itself expensive; (b) ~50k period rows carry responses (`first_seen_at` is scrape time, so almost every review falls inside a 30-day window), and shipping two timestamps per row cost 315 ms; (c) each separate `GROUP BY` was a full-table aggregate scan costing 30–100 ms, so the block count set the floor.

**Decision**: (a) drop the `IN` clause when no org/company filter is set; (b) compute the response delay in SQL and derive avg/SLA from `SUM`/`COUNT`, with percentiles via `percentile_cont` on PostgreSQL; (c) merge every counter and distribution into one `GROUP BY (platform, rating, sentiment)` scan with `CASE` conditionals for the period and 24h/2h/today windows.

**Measured**: service path 5.0 s → 241 ms (min, warm); HTTP end-to-end 5.5 s → ~0.27 s; platform-filtered 8.0 s → ~0.27 s. Payload verified identical to the pre-change implementation across 9 parameter combinations on production data.

## R9 — Tie ordering in trending aspects

**Finding**: verification against the pre-change implementation surfaced exactly one difference — two problem categories with equal mention counts came out in a different order. Both implementations sorted only by `mentions`, so the tie fell back to row arrival order, which neither the ORM nor the database promises.

**Decision**: break the tie on category name (`sort(key=lambda a: (-a["mentions"], a["category"]))`). This makes the block deterministic rather than reproducing the old nondeterminism; it is the one intentional behavior change and it only affects the order of equal-count entries.

## R7 — Ordering & rounding identity risks

**Finding**: payload identity (FR-001) can break on (a) tie ordering — `_worst_locations` uses Python's stable sort over the org list; SQL `ORDER BY` tie order is unspecified; (b) float rounding — Python `round()` (banker's rounding) vs SQL `ROUND()` differ on .5 cases; (c) `avg_per_day`/percent formulas.

**Decision**: SQL returns raw integer counts / raw sums only; **all** rounding, percent math, sorting, and top-N slicing stay in the existing Python code paths. `_worst_locations`/`_platform_cards`/`_attention` keep their current loops over `orgs` (tens of rows) and consume SQL-derived count maps.
