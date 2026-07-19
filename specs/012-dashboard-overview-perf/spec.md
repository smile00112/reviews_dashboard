# Feature Specification: Dashboard Overview Performance

**Feature Branch**: `012-dashboard-overview-perf`

**Created**: 2026-07-19

**Status**: Draft

**Input**: User description: "Dashboard overview endpoint performance: rewrite DashboardService.overview aggregation to push counts/distributions to SQL instead of loading all Review ORM rows into Python (currently ~5s response). Scope: SQL GROUP BY / FILTER aggregates for header, kpi_hero, rating_distribution, sentiment, unanswered counts; narrow column loading for the remaining per-review blocks (kpi_strip response times, trending aspects 14-day window); composite/partial indexes; no behavior change — identical JSON payload, target <300ms."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast overview load (Priority: P1)

An operator opens the network overview dashboard (any period/platform filter combination). The page renders its metrics without a multi-second wait, so the operator can check the network state several times a day without friction.

**Why this priority**: This is the whole feature. The overview is the team's primary landing page; a ~5-second wait on every filter change makes the dashboard feel broken and discourages use.

**Independent Test**: Request the overview with the default filters (30-day period, all platforms) against a realistically sized dataset and measure server response time; compare the response body with the pre-change body for the same data.

**Acceptance Scenarios**:

1. **Given** a database with the current production-scale review volume, **When** the overview is requested with `period=30d&platform=all`, **Then** the server responds in under 300 ms.
2. **Given** the same database state, **When** the overview is requested before and after this change with identical parameters, **Then** both responses carry the same values in every block (header, KPIs, rating distribution, sentiment, platform cards, attention feed, worst locations, trending aspects).
3. **Given** any valid combination of `period`, `platform`, `org_ids`, `company_id`, **When** the overview is requested, **Then** the response matches the pre-change response for the same parameters and data.

---

### User Story 2 - Filtered views stay fast (Priority: P2)

An operator narrows the overview to a single platform, a company, or a hand-picked set of organizations. Filtered requests are at least as fast as the unfiltered one — narrowing the scope never makes the dashboard slower.

**Why this priority**: Filter changes are the most frequent interaction on the page; today a platform-specific filter triggers a second full data scan and can be slower than the unfiltered view.

**Independent Test**: Request the overview with `platform=yandex` (and with `company_id` / `org_ids` filters) and confirm response time is within the same budget as the unfiltered request.

**Acceptance Scenarios**:

1. **Given** production-scale data, **When** the overview is requested with a specific platform filter, **Then** the response time stays under the same 300 ms budget and the payload matches the pre-change payload.
2. **Given** an empty selection (filters matching no organizations), **When** the overview is requested, **Then** the empty payload is returned immediately with all-zero blocks, as today.

---

### Edge Cases

- Organizations with zero reviews: all aggregates must return the same zeros/nulls as the current Python logic (no division-by-zero, no missing keys).
- Reviews with `rating` NULL: excluded from rating distribution and reputation index exactly as today.
- Reviews with no analysis fields (`sentiment` NULL): counted as "neutral" by the existing summarize logic — aggregate must reproduce that, not silently drop them.
- Naive vs. aware timestamps: the test suite runs on SQLite where timestamps are naive; time-window comparisons must behave identically on both backends.
- `period=all` (no cutoff): aggregates must cover all rows without a time filter.
- Removed reviews (`removed_at` set): whatever the current behavior is (included in overview scans today), the rewritten aggregates must preserve it byte-for-byte — this feature does not change removal semantics.
- Reviews with `first_seen_at` exactly on a window boundary: boundary operators (`>=`/`<=`) must match the current Python comparisons.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The overview endpoint MUST return a payload identical in structure and values to the current implementation for any given database state and parameter combination (regression-invariant rewrite).
- **FR-002**: Count- and distribution-style blocks (header counters, KPI hero counters, rating distribution, sentiment distribution, per-organization unanswered counts) MUST be computed by the database, not by iterating review rows in application code.
- **FR-003**: Blocks that genuinely need per-review data (response-time percentiles, trending aspects / aspect spikes over the last 14 days) MUST load only the fields they need and only the rows in the relevant time window, not full review records for all time.
- **FR-004**: A platform-filtered request MUST NOT scan more data than the unfiltered request (removal of the second full scan in platform cards).
- **FR-005**: The database MUST have indexes supporting the new aggregate queries so they remain fast as review volume grows.
- **FR-006**: The rewrite MUST behave identically on the production database engine and on the lightweight engine used by the automated test suite.
- **FR-007**: Existing overview and attention-rule test suites MUST pass unchanged (they are the behavioral contract).

### Key Entities

- **Review**: the row set being aggregated; relevant attributes: organization, platform, rating, first-seen timestamp, response text/timestamp, sentiment fields, problems list, review date.
- **Organization**: filter scope and source of per-platform rating/count columns (unchanged).
- **Rating snapshot**: unchanged; already aggregated in a single query.
- **Attention rule**: unchanged in behavior; its evaluation may consume the narrowed per-review data instead of full records.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Overview response time at current production data volume drops from ~5 s to under 300 ms for the default view (95th percentile under 500 ms).
- **SC-002**: Overview responses before and after the change are value-identical across all parameter combinations exercised by the existing test suite (100% of existing tests pass without modification).
- **SC-003**: Peak memory used per overview request no longer grows linearly with total review count (no full-table materialization).
- **SC-004**: Platform-filtered requests are no slower than the unfiltered request on the same data.

## Assumptions

- Current behavior (including any quirks, e.g. removed reviews being included in overview aggregates) is the contract; this feature changes performance only, never values.
- "Production scale" is the current deployment: ~tens of organizations, tens of thousands of reviews; the target must hold with 10× that volume.
- The existing `generated_at` timestamp naturally differs between two live responses; payload comparison excludes it.
- A short-TTL response cache is out of scope for this feature (may be a follow-up); the target must be met by query efficiency alone.
- No API contract change: same route, same parameters, same response schema.
