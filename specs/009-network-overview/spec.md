# Feature Specification: Network Overview Dashboard

**Feature Branch**: `009-network-overview`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: Network overview dashboard page ("Обзор" / screen-overview), first page of the GeoMonitor SERM dashboard prototype — a read-only network-level analytics landing page aggregating review data across all organization branches, with period / platform / organization filters.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - At-a-glance network health on landing (Priority: P1)

An operator opens the dashboard and immediately sees the health of the whole review network: the network average rating, how many new reviews arrived in the selected period, and how many reviews are still unanswered. Headline counts (new reviews, unanswered > 24h, fresh negatives) appear in a greeting line so nothing critical is missed.

**Why this priority**: This is the reason the page exists — the single screen an operator checks first each day. Without the headline KPIs the page delivers no value. It is a self-contained MVP: even with nothing else, the operator gets an actionable pulse of the network.

**Independent Test**: Load the overview with seeded reviews across several organizations; verify the greeting counts, the three hero KPIs, and the five secondary KPIs render correct aggregated numbers for the default period (30 days), and that a network with zero reviews shows zeroed values rather than errors.

**Acceptance Scenarios**:

1. **Given** reviews exist across multiple organizations, **When** the operator opens the overview, **Then** the network average rating, new-reviews-in-period count, total reviews, and unanswered count are shown as network-wide aggregates.
2. **Given** some reviews have no business response and are older than 24 hours, **When** the page loads, **Then** the "unanswered" KPI and the "overdue > 24h" sub-count reflect exactly those reviews.
3. **Given** negative reviews (≤ 2 stars) arrived within the last 2 hours, **When** the page loads, **Then** the greeting line reports that fresh-negative count.
4. **Given** the network has no reviews at all, **When** the page loads, **Then** all KPIs show zero/neutral values and no error is displayed.

---

### User Story 2 - Distribution and sentiment breakdown (Priority: P2)

The operator wants to understand the shape of the reviews: how ratings are distributed 1–5 stars, the positive/neutral/negative sentiment split, and how reviews are spread across platforms (Yandex / 2GIS / Google).

**Why this priority**: Distribution and sentiment give the "why" behind the headline average. Valuable but secondary to the headline pulse; the page is still useful without it.

**Independent Test**: With seeded reviews of mixed ratings and sentiments, verify the star-distribution bars, the sentiment donut counts, and the platform review-count donut all sum to the network totals and match per-star / per-sentiment / per-platform counts.

**Acceptance Scenarios**:

1. **Given** reviews of varied star ratings, **When** the page loads, **Then** the 1–5★ distribution shows per-star counts and percentages plus the 4–5★ and 1–3★ share summaries.
2. **Given** reviews carry sentiment labels, **When** the page loads, **Then** the sentiment breakdown shows positive/neutral/negative counts that sum to the analyzed-review total.
3. **Given** reviews and organizations exist on multiple platforms, **When** the page loads, **Then** the platform breakdown shows the review count per platform.
4. **Given** a per-platform metric has no underlying data (e.g. Google per-review negativity), **When** the page loads, **Then** that metric shows a "нет данных" placeholder instead of a fabricated number.

---

### User Story 3 - Prioritized attention feed (Priority: P2)

The operator wants a single ranked list of things that need a reaction in the last 24 hours: reviews unanswered beyond SLA, newly arrived negatives, escalated reviews, points whose rating dropped, and aspects whose negative mentions are spiking. Each item links to the relevant detail screen.

**Why this priority**: Turns analytics into action. High operator value, but depends on the underlying counts from P1, so it follows.

**Independent Test**: Seed conditions for each attention type; verify each surfaces as an item with the correct count, ordered by criticality, and that items link to the reviews or organization detail screens.

**Acceptance Scenarios**:

1. **Given** reviews unanswered > 24h exist, **When** the page loads, **Then** an attention item reports their count and links to the reviews screen.
2. **Given** reviews were escalated, **When** the page loads, **Then** an attention item reports the escalated count.
3. **Given** an aspect's negative mentions rose over the last 7 days versus the prior 7 days, **When** the page loads, **Then** an attention item reports that aspect and its percentage growth.
4. **Given** rating-history data has not yet accrued, **When** a rating-drop item cannot be computed, **Then** that item is omitted rather than shown with an empty delta.

---

### User Story 4 - Worst locations and trending negative aspects (Priority: P3)

The operator wants to know which points are dragging the network down (lowest rating, most unanswered) and which complaint aspects are trending negative, so managerial attention can be directed.

**Why this priority**: Deep-dive lists for follow-up. Useful but the least time-critical of the blocks.

**Independent Test**: Seed organizations with varied ratings and unanswered counts, and reviews with categorized problems across two 7-day windows; verify the top-10 worst-locations table orders by rating ascending with unanswered counts, and the trending-aspects table shows week-over-week change per aspect with a sentiment split.

**Acceptance Scenarios**:

1. **Given** organizations with varied ratings, **When** the page loads, **Then** the worst-locations table lists up to 10 organizations ordered by rating ascending, each with its rating and unanswered count.
2. **Given** categorized problems across reviews in two consecutive 7-day windows, **When** the page loads, **Then** the trending-aspects table shows each aspect's mention count, week-over-week change, and positive/neutral/negative split.

---

### User Story 5 - Filtering the whole view (Priority: P2)

The operator narrows the entire overview by time period (day / week / 30 days / 90 days / year / all time), by platform (all / Yandex / Google / 2GIS), and by one or more organizations. Every block on the page recomputes for the active filters.

**Why this priority**: Filters multiply the value of every other block and are expected of an analytics landing page, but the default (all organizations, 30 days, all platforms) is useful on its own, so filtering is an enhancement over the P1 default view.

**Independent Test**: Change each filter and verify all blocks recompute; verify the organization filter narrows aggregates to only the selected organizations, and the platform filter narrows to the selected platform.

**Acceptance Scenarios**:

1. **Given** the default view, **When** the operator selects a different period, **Then** all counts, distributions, and deltas recompute for that window.
2. **Given** the default view, **When** the operator selects a single platform, **Then** all blocks reflect only that platform's data.
3. **Given** the default view, **When** the operator selects one or more organizations, **Then** all aggregates are restricted to the selected organizations.

---

### Edge Cases

- Network with zero reviews → all blocks show zero/neutral, no errors.
- Selected organization has no reviews in the period → blocks show zeroed values for that selection.
- Rating history not yet accrued (fresh install) → all period-over-period rating deltas render empty ("—"), not zero or fabricated.
- Reviews missing a review date → excluded from date-windowed computations without breaking totals.
- Reviews not yet analyzed (no sentiment) → excluded from sentiment percentages but still counted in raw totals.
- Response-time metrics rely on an approximate observation timestamp → labelled as approximate, never presented as exact reply latency.
- A platform lacks per-review data (Google/2GIS) → per-review-derived metrics for it show "нет данных".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present a read-only network overview aggregating review data across all organization branches by default.
- **FR-002**: System MUST show a greeting header with live counts: new reviews in the selected period, reviews unanswered beyond 24 hours, and negative reviews (≤ 2 stars) arrived in the last 2 hours.
- **FR-003**: System MUST show three headline KPIs: network average rating (weighted by review volume), new reviews in the selected period, and total unanswered reviews (with an overdue > 24h sub-count).
- **FR-004**: System MUST show five secondary KPIs: average response time, median response time, response-time p95, share of reviews answered within SLA, positivity share, and reputation index (share of 5★ minus share of 1–3★). Response-time metrics MUST be labelled approximate.
- **FR-005**: System MUST show the rating distribution across 1–5 stars with per-star counts and percentages, plus 4–5★ and 1–3★ share summaries.
- **FR-006**: System MUST show a sentiment breakdown (positive / neutral / negative) derived from stored review analytics, counting only analyzed reviews.
- **FR-007**: System MUST show a review-count breakdown by platform (Yandex / 2GIS / Google).
- **FR-008**: System MUST show a per-platform aggregate card for each of Yandex, Google, and 2GIS with weighted average rating; metrics without underlying data MUST render a "нет данных" placeholder.
- **FR-009**: System MUST show a prioritized "attention" feed for the last 24 hours including: reviews unanswered > 24h, freshly arrived negatives, escalated reviews, rating drops, and aspects with rising negative mentions; each item MUST link to the relevant detail screen.
- **FR-010**: System MUST show a top-10 worst-locations table ordered by rating ascending, each row with rating, period rating delta (when available), and unanswered count.
- **FR-011**: System MUST show a trending-negative-aspects table comparing the last 7 days to the prior 7 days, with each aspect's mention count, change, and positive/neutral/negative split.
- **FR-012**: Users MUST be able to filter the entire overview by time period (day / week / 30 days / 90 days / year / all time), and every block MUST recompute for the selected period.
- **FR-013**: Users MUST be able to filter the entire overview by platform (all / Yandex / Google / 2GIS).
- **FR-014**: Users MUST be able to filter the entire overview by one or more organizations, restricting all aggregates to the selection.
- **FR-015**: System MUST record daily rating history per organization and platform so that period-over-period rating deltas can be computed; deltas MUST render empty until sufficient history exists.
- **FR-016**: System MUST compute the "answered within SLA" share against a fixed configured time threshold.
- **FR-017**: System MUST degrade safely: missing, unanalyzed, or dateless data MUST be excluded from the relevant computation without raising errors or corrupting totals.
- **FR-018**: The overview MUST remain strictly read-only — it MUST NOT publish, edit, or delete reviews or responses on any provider.

### Key Entities *(include if feature involves data)*

- **Organization (branch)**: An individual reviewed location; carries current per-platform ratings and review counts, city/region, and franchise flag. The unit that aggregates roll up from.
- **Company**: Optional parent grouping organizations (branches); may scope the organization filter.
- **Review**: A collected review with star rating, text, dates, business response presence, triage status (new / in progress / answered / escalated), platform, and derived analytics (sentiment, categorized problems).
- **Rating snapshot**: A new daily record of an organization's rating and review count per platform, enabling period-over-period rating deltas. Accrues over time; empty on first use.
- **Attention item**: A derived, non-persisted alert (unanswered overdue, fresh negative, escalated, rating drop, aspect spike) surfaced in the attention feed.
- **Aspect / problem category**: A categorized complaint topic extracted from review analytics, aggregated over time windows for trend detection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can identify the network's average rating, new-review volume, and unanswered backlog within 5 seconds of the page loading, without scrolling.
- **SC-002**: Every displayed aggregate (KPI counts, distribution totals, sentiment totals, platform totals) reconciles exactly to the underlying reviews for the active filters.
- **SC-003**: Changing any filter (period, platform, organization) recomputes all blocks and returns an updated view in under 2 seconds for a network on the order of tens of organizations.
- **SC-004**: A freshly installed network (no rating history) displays the page with all rating deltas empty and no errors, and begins showing month-over-month deltas once ~30 days of history have accrued.
- **SC-005**: 100% of blocks whose data is unavailable (competitor benchmark, Google/2GIS per-review metrics) show an explicit "нет данных" placeholder rather than a fabricated or zero value that could be misread as real.
- **SC-006**: The attention feed surfaces every review unanswered > 24h and every escalated review currently in the network, with counts matching the underlying data.

## Assumptions

- Aggregation defaults to all organizations, the last 30 days, and all platforms when no filters are applied (matches the prototype's default state).
- "Unanswered" means a review with no stored business response; response presence is derived from stored data, not fetched live.
- Response-time metrics are approximate, derived from the observation timestamp of when a response was first seen (scrape-interval granularity), not an exact provider reply timestamp.
- The SLA threshold is a fixed constant (assumed 24 hours) rather than a per-organization configurable value in this iteration.
- Google Maps remains excluded as a *collection* provider (constitution). Google figures shown here are display-only of already-stored, operator-entered aggregate values; where no per-review Google data exists, metrics show "нет данных". No Google scraping is introduced.
- Competitor "vs рынок" benchmarking has no data source and is shown as "нет данных" / omitted in this iteration.
- Rating history begins accruing from feature deployment; historical deltas covering periods before deployment are not backfilled.
- The page reuses the existing authenticated control panel and RBAC; no new authentication is introduced.
- Charts are rendered without adding a new charting dependency.
- Sentiment and problem categories come from the existing deterministic, local analytics; no new LLM/external analysis is introduced.
