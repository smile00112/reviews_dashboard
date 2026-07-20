# Feature Specification: Ratings Page

**Feature Branch**: `014-ratings-page`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Ratings page (screen-rating from the dashboard prototype): a new dashboard page at /ratings showing comparative rating analysis across platforms. Five blocks: (1) platform distribution table; (2) rating dynamics; (3) review volume; (4) response speed; (5) weekday breakdown. Filters: period, platform, org/company — same as the overview page. Out of scope: hour-of-day heatmap, Google/2GIS per-review scraping, chart library, SLA-config UI."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare rating quality across platforms (Priority: P1)

An operator opens the Ratings page and sees, in one table, how each platform (Yandex, 2ГИС, Google) rates for the selected organizations: the average rating and the share of 5★ down to 1★ reviews, plus how many reviews have been removed. This lets them tell at a glance which platform drags reputation down and whether low stars concentrate on one platform.

**Why this priority**: The comparative distribution table is the core reason the page exists — it is the only place that puts per-platform rating quality side by side. It is viable on its own even if every other block is absent.

**Independent Test**: Load the page for a set of organizations that have collected reviews and platform aggregates; confirm the table shows one row per platform with an average rating, a per-star breakdown and removed count for the collected platforms (Yandex, 2ГИС), and an aggregate-only row for Google — with «нет данных» wherever per-review data does not exist.

**Acceptance Scenarios**:

1. **Given** organizations with collected reviews of mixed ratings, **When** the operator opens the Ratings page, **Then** each collected platform's row shows an average rating and per-star shares (5★…1★) that account for all its active reviews, plus its count of removed reviews.
2. **Given** Google has only an aggregate rating and review count (no per-review data, since it has no collector), **When** the table renders, **Then** its row shows the aggregate average rating but displays «нет данных» for the per-star breakdown and removed count.
3. **Given** a platform filter is set to a single platform, **When** the table renders, **Then** only that platform's row is shown and all other blocks reflect the same platform scope.

---

### User Story 2 - See how ratings and volume trend over time (Priority: P2)

The operator wants to know whether reputation is improving or slipping. Two time-series blocks show, per platform, the monthly average rating (dynamics) and the monthly review count (volume), so trends and their drivers are visible together.

**Why this priority**: Trend context turns a static snapshot into a direction. It depends on accrued daily snapshot history, so it delivers less on day one than the distribution table, but it is the second-most valuable view.

**Independent Test**: With at least two months of captured rating snapshots for a platform, confirm the dynamics block plots one line per platform of monthly average rating and the volume block plots monthly review counts per platform, both bounded by the selected period.

**Acceptance Scenarios**:

1. **Given** rating snapshots exist across several months, **When** the operator views the dynamics block, **Then** each platform is drawn as a separate monthly average-rating series over the selected period.
2. **Given** snapshot history is shorter than the selected period, **When** the blocks render, **Then** only the months with data appear and the blocks do not error or fabricate values.
3. **Given** no snapshot history exists yet, **When** the blocks render, **Then** they show an empty/"data accruing" state rather than failing.

---

### User Story 3 - Judge responsiveness and timing patterns (Priority: P3)

The operator wants to know how fast the team answers reviews and when negative reviews cluster. A response-speed block shows the weekly median and 95th-percentile response time against a fixed service-level target, and a weekday breakdown shows review volume and average rating per day of week with a short best/worst-day insight.

**Why this priority**: These are supporting diagnostics — useful for operational tuning but not the primary reputation read. Response data exists only for Yandex, and weekday timing is coarse, so this block is intentionally last.

**Independent Test**: With Yandex reviews carrying response timestamps and review dates, confirm the response-speed block shows weekly median/p95 versus the target line, and the weekday block shows seven days with counts, average ratings, and an insight naming the best and worst weekday.

**Acceptance Scenarios**:

1. **Given** Yandex reviews with recorded response times, **When** the response-speed block renders, **Then** it shows a weekly median series and a weekly p95 series compared against a constant target.
2. **Given** reviews carry a calendar review date, **When** the weekday block renders, **Then** it shows one entry per weekday (Mon–Sun) with review count and average rating, and an insight identifying the worst-rated and best-rated weekday.
3. **Given** the selected organizations have no reviews in the period, **When** the response and weekday blocks render, **Then** they show empty states rather than errors.

---

### Edge Cases

- **No organizations match the filter** (empty network or over-narrow company/org filter) → all blocks render zeroed/empty states, no errors.
- **A platform has an average rating but zero stored per-review rows** (Google) → per-star and removed columns show «нет данных», the aggregate rating still shows.
- **Reviews with no parsed `review_date`** → excluded from the weekday breakdown (which needs a date) but still counted in the distribution table.
- **Only removed reviews remain for a platform** → distribution reflects active reviews only (removed excluded from per-star shares), the removed count reflects the removed rows.
- **Custom period with an invalid or reversed date range** → falls back to the default period, consistent with the overview page's behavior.
- **Snapshot history younger than the selected period** → trend blocks show the available months only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a Ratings page reachable from the main dashboard navigation, scoped by the same filters as the overview page: time period, platform, and organization/company selection.
- **FR-002**: The page MUST present a platform-distribution table with one row per platform showing the average rating, the percentage share of each star level (5★ through 1★), and the count of removed reviews.
- **FR-003**: For platforms whose reviews are collected individually (Yandex, 2ГИС), per-star shares and removed counts MUST be computed from the actual review records for the selected organizations and period; only active (non-removed) reviews contribute to the per-star shares.
- **FR-004**: For platforms that expose only an aggregate rating and review count (Google, which has no collector), the table MUST show the aggregate average rating and MUST display «нет данных» for the per-star breakdown and removed count rather than fabricating values.
- **FR-005**: The page MUST present a rating-dynamics block showing, per platform, the average rating over time (monthly granularity) bounded by the selected period, sourced from captured daily rating history.
- **FR-006**: The page MUST present a review-volume block showing, per platform, the review count over time (monthly granularity) bounded by the selected period.
- **FR-007**: The page MUST present a response-speed block showing the median and 95th-percentile response time to reviews over time (weekly granularity) for the platform(s) that record response times, compared against a fixed service-level target.
- **FR-008**: The page MUST present a weekday breakdown showing, for each day of the week (Mon–Sun), the review count and average rating for the selected organizations and period, plus a short insight naming the worst-rated and best-rated weekday.
- **FR-009**: The weekday breakdown MUST be derived from each review's calendar review date; it MUST NOT claim a time-of-day dimension, since posting time is not recorded.
- **FR-010**: All blocks MUST honor the active filters consistently — a change to period, platform, or organization/company selection MUST update every block on the page.
- **FR-011**: Every block MUST degrade to an explicit empty or «нет данных» state (never an error or a misleading zero-as-data) when the underlying data is absent for the current filter.
- **FR-012**: Filter selections MUST be reflected in the page's shareable location (URL) so a filtered view can be bookmarked and reopened, consistent with the overview page.
- **FR-013**: The page MUST NOT trigger any new data collection; it reads only already-stored reviews, platform aggregates, and rating history.

### Key Entities *(include if feature involves data)*

- **Review**: An individual review for an organization on a platform, with a star rating, an optional calendar review date, response timing, and a removal marker. Source for Yandex per-star distribution, response speed, and weekday breakdown.
- **Organization platform aggregate**: The per-organization stored average rating and review count for each platform (used for Google/2ГИС rows and as the current rating for all platforms).
- **Rating snapshot**: A daily-captured record of an organization's rating and review count per platform, forming the history that powers the dynamics and volume trend blocks.
- **Ratings view payload**: The composed, filter-scoped result the page consumes: the platform distribution rows, the two trend series sets, the weekly response-speed series, and the weekday breakdown with its insight.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can identify, in a single view and within 10 seconds, which platform has the weakest rating and the largest share of 1–2★ reviews for the selected organizations.
- **SC-002**: The platform-distribution per-star shares for a platform sum to the platform's active review total (no review is double-counted or dropped), verifiable against the raw review data.
- **SC-003**: Changing any filter (period, platform, organization/company) updates every block on the page consistently, with no block retaining stale scope.
- **SC-004**: The page loads and renders all available blocks in under 1 second for the full network at current data volume (tens of organizations, tens of thousands of reviews).
- **SC-005**: Every block that lacks data for the current filter shows an explicit empty or «нет данных» state, with zero blocks erroring, across all filter combinations.
- **SC-006**: The page performs no writes and initiates no scraping — it is strictly read-only.

## Assumptions

- The Ratings page reuses the overview page's filter model (period presets plus custom range, platform, organization/company) and its read-only, internal-tool posture (no application auth).
- Yandex and 2ГИС reviews are stored as individual records (both have collectors); Google contributes an aggregate rating and review count only, because it has no collector and remains out of collection scope. This mirrors the current scraping scope and is not changed by this feature.
- Daily rating snapshots are already being captured (as introduced by the overview feature); trend blocks show whatever history has accrued and improve as history grows.
- Response-time data exists for the collected platforms (Yandex, 2ГИС); the response-speed block covers them and shows an empty state when no answered reviews fall in scope. Response delay is measured from when the scraper first saw the review, so it is an approximation for back-filled data.
- The service-level target for response speed is a fixed constant (reused from the overview page), not a user-configurable setting.
- Weekday is derived from the parsed calendar review date; reviews without a parsed date are omitted from the weekday block only.
- Time-of-day analysis is out of scope because reviews carry no posting time; the prototype's hour×weekday heatmap is intentionally reduced to a weekday-only breakdown.
- Charts are rendered without introducing a new charting dependency, consistent with the overview page.
