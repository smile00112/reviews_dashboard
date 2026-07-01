# Feature Specification: HTTP Review Scraper (public_http mode)

**Feature Branch**: `003-http-scraper`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "HTTP requests-based Yandex review scraper as a new public_http scrape mode with a dedicated web page, ported from BrandTrackerAI MultiPageYandexParser, persisting to the same per-organization Review store"

## Context

The sibling `BrandTrackerAI_Parser` has a **working** browserless Yandex review scraper
(`MultiPageYandexParser`): plain `requests` + BeautifulSoup, paginating via `?page=N`.
It currently produces real output (hundreds of reviews). This feature ports that approach
into ReviewsDashboard as a new scrape mode `public_http`, exposed through a dedicated web
page, **in addition to** the existing Playwright `public` and `operator_auth` modes (those
stay). Reviews persist to the same per-organization `Review` store with the existing dedup
and analytics (feature 002).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scrape an organization via HTTP, no browser (Priority: P1)

An operator opens a dedicated "HTTP Scraper" page, picks an existing organization, and
runs a browserless scrape. Reviews are fetched over plain HTTP (paginated), parsed,
deduplicated, analyzed, and stored exactly like other scrapes; a `ScrapeRun` records the
outcome.

**Why this priority**: This is the whole feature — a faster, dependency-light scrape path
that already works in the source project.

**Independent Test**: Trigger a `public_http` scrape for an org against fixture HTML; assert
reviews are stored with `scrape_mode=public_http`, a `ScrapeRun` is recorded with counts,
and dedup/analytics behave as for other modes.

**Acceptance Scenarios**:

1. **Given** an existing organization with a Yandex URL, **When** an operator runs an HTTP scrape from the page, **Then** a `ScrapeRun` is created with `mode=public_http` and, on success, reviews are stored for that organization.
2. **Given** a second HTTP scrape of the same organization, **When** it runs, **Then** already-seen reviews are deduplicated (updated, not re-inserted) by `content_hash`.
3. **Given** stored reviews from an HTTP scrape, **When** viewed, **Then** they carry sentiment/problems analysis like any other review (feature 002).

---

### User Story 2 - Dedicated page separate from existing flow (Priority: P2)

The HTTP scraper has its own web page/tab, distinct from the existing organizations/scrape
flow: list organizations, trigger an HTTP scrape, watch run status, and view that org's
resulting reviews.

**Why this priority**: The user asked for a separate interface; it isolates the new path so
it can be evaluated without disturbing the existing dashboard.

**Independent Test**: Load the page, trigger a scrape for an org, observe run status update
to a terminal state, and see the org's reviews listed.

**Acceptance Scenarios**:

1. **Given** the HTTP Scraper page, **When** loaded, **Then** it lists existing organizations with a per-org HTTP-scrape action.
2. **Given** a triggered HTTP scrape, **When** it completes, **Then** the page reflects the run's terminal status and shows the org's reviews.

---

### Edge Cases

- **Bot protection / access challenge** (e.g. page contains "Обнаружена защита от ботов" or captcha markers) → run ends `needs_manual_action` with an HTML debug artifact, NOT `failed`, and NEVER a silent retry or bypass (constitution IV).
- A page returns no review blocks → that page is skipped; the run still completes with whatever was collected (possibly zero).
- Network error / non-200 on a page → that page is skipped (logged); the run succeeds with partial data, or fails only if the first page is unreachable.
- Reaching the configured `limit` stops pagination early.
- HTTP markup differs from the Playwright DOM → parser returns nothing for that page rather than crashing (safe-degrade).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST add a new scrape mode `public_http` to `ScrapeMode`, selectable per-organization, without removing or altering `public` or `operator_auth`.
- **FR-002**: System MUST provide a browserless scraper that fetches an organization's Yandex reviews over HTTP with pagination (`?page=N`), bounded by configurable `limit` and `max_pages`, with a polite inter-page delay.
- **FR-003**: The HTTP scraper MUST parse reviews from page HTML using the existing structured parser (`parse_reviews_from_html`) and return the standard `ScrapeResult` (organization + reviews).
- **FR-004**: HTTP scrapes MUST persist through the existing `ReviewService.upsert_reviews` path so dedup (`content_hash`) and analytics (feature 002) apply unchanged, tagging reviews `scrape_mode=public_http`.
- **FR-005**: Every HTTP scrape MUST produce a `ScrapeRun` with status, timestamps, and counts, consistent with other modes.
- **FR-006**: Bot protection / access challenges MUST surface as `needs_manual_action` with a saved HTML debug artifact; the scraper MUST NOT attempt captcha bypass.
- **FR-007**: The existing scrape trigger endpoint MUST accept `mode=public_http` (no new endpoint required); background-task execution and `ScrapeRun` polling are reused.
- **FR-008**: The web app MUST expose a dedicated page for HTTP scraping: list organizations, trigger a `public_http` scrape, show run status, and display the org's reviews.
- **FR-009**: HTTP scraper parameters (user-agent/headers, `limit`, `max_pages`, request delay) MUST be configurable via settings with sensible defaults (limit 150, max_pages 5).

### Key Entities *(include if feature involves data)*

- **ScrapeMode.public_http**: New enum value; no new tables. Reuses `ScrapeRun` and `Review` exactly as existing modes do.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running a `public_http` scrape on fixture HTML stores reviews tagged `scrape_mode=public_http` and records a successful `ScrapeRun` with non-zero counts.
- **SC-002**: A second identical HTTP scrape inserts 0 new reviews (all deduplicated).
- **SC-003**: A page containing a bot-protection marker yields a `needs_manual_action` run with a debug HTML path, and 0 unhandled exceptions.
- **SC-004**: The existing Playwright `public` and `operator_auth` modes continue to work unchanged (existing tests stay green).
- **SC-005**: An operator can complete a full HTTP scrape of one organization from the dedicated page and see its reviews without touching the existing organizations flow.

## Assumptions

- The `?page=N` HTTP responses contain the same `business-review-view` markup the feature-002 parser already handles (validated by the source project's real output).
- Browserless HTTP works for the target organizations; when Yandex serves a challenge instead, `needs_manual_action` is the correct, expected outcome (operators can fall back to a Playwright mode).
- The page operates on existing organizations only; no organization auto-creation in this feature.
- Background-task execution (not synchronous) is used, matching existing scrape flow.
- 2GIS and the source project's scheduler/CSV output are explicitly NOT ported (out of scope per constitution).
