# Feature Specification: 2GIS Review Collection (twogis_api mode)

**Feature Branch**: `006-2gis-reviews`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User request: "add ScrapeOps for 2gis" — collect 2GIS organization reviews the
same way Yandex reviews are collected, after investigation showed 2GIS is served by a
public JSON reviews API rather than the Yandex HTML the existing parser understands.

## Context

The existing scrapers (Yandex `public`, `operator_auth`, `public_http`, `scrapeops`) are
Yandex-only: their parser keys off `business-review-view` DOM and the org-root HTML.
Pointing any of them at a 2GIS URL yields **zero reviews** — 2GIS is a different provider
with a heavy React SPA that bot-walls direct HTML fetches (HTTP 403 from a datacenter IP).

Investigation found 2GIS exposes reviews through **public JSON APIs**, no HTML parsing and
no captcha:

- **Catalog**: `GET catalog.api.2gis.com/3.0/items/byid?id={firm_id}&key={catalog_key}&fields=items.org,items.reviews,items.point` → resolves a branch/firm id to its **org id**, plus name, rating, and review counts.
- **Reviews**: `GET public-api.reviews.2gis.com/3.0/orgs/{org_id}/reviews?key={review_key}&limit=&offset=&sort_by=date_created&rated=true` → paginated review objects (`user.name`, `rating`, `text`, `date_created`, `official_answer`, `id`), pagination via `meta.next_link`.

2GIS reviews are **org-level** (aggregated across an organization's branches); two branch
short links of the same org resolve to the same `org_id` and the same review pool. That is
the correct unit for this product, which tracks organizations.

This feature adds a new scrape mode `twogis_api` that fetches 2GIS reviews via these APIs
and persists them through the **existing** `ReviewService.upsert_reviews` path, so dedup
(`content_hash`), normalization, and analytics (feature 002) apply unchanged. Constitution
amended to v1.3.0 (Principle VIII, Multi-Provider Collection) to bring 2GIS in scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Collect an organization's 2GIS reviews (Priority: P1)

An operator adds an organization with a 2GIS URL (full `…/firm/{id}` URL or a
`go.2gis.com/CODE` short link) and runs a `twogis_api` scrape. Reviews are fetched from the
2GIS reviews API, deduplicated, analyzed, and stored exactly like Yandex reviews; a
`ScrapeRun` records the outcome.

**Why this priority**: This is the whole feature — bringing a second provider's reviews
into the same dashboard.

**Independent Test**: Run a `twogis_api` scrape for an org whose URL points at 2GIS against
recorded API fixtures; assert reviews are stored with `scrape_mode=twogis_api`, a
`ScrapeRun` records counts, and dedup/analytics behave as for other modes.

**Acceptance Scenarios**:

1. **Given** an organization with a 2GIS firm URL, **When** an operator runs a `twogis_api` scrape, **Then** a `ScrapeRun` is created with `mode=twogis_api` and, on success, org-level reviews are stored for that organization.
2. **Given** a second `twogis_api` scrape of the same organization, **When** it runs, **Then** already-seen reviews are deduplicated (updated, not re-inserted) by `content_hash`.
3. **Given** stored 2GIS reviews, **When** viewed, **Then** they carry sentiment/problems analysis like any other review (feature 002), and any 2GIS `official_answer` is stored as the display-only `response_text`.

---

### User Story 2 - Short-link resolution (Priority: P2)

An operator pastes a `go.2gis.com/CODE` short link (2GIS's default share format). The
scraper resolves it to the underlying firm id and proceeds as for a full URL.

**Why this priority**: Short links are what 2GIS's UI hands out; requiring the full firm
URL would be a sharp edge.

**Independent Test**: Given a short-link URL and a recorded resolution, assert the scraper
derives the same `firm_id` → `org_id` and collects reviews.

**Acceptance Scenarios**:

1. **Given** a `go.2gis.com/CODE` URL, **When** a `twogis_api` scrape runs, **Then** the firm id is resolved (via the ScrapeOps proxy, since 2GIS bot-walls direct SPA fetches) and reviews are collected.
2. **Given** a full `…/firm/{id}` URL, **When** a scrape runs, **Then** the firm id is taken from the URL directly with no proxy call.

---

### Edge Cases

- **No firm id resolvable** (bad URL, short link that will not resolve even via proxy) → run ends `failed` with a clear `error_code`, never a silent empty success.
- **Catalog key blocked / API rejects key** (403 `apiKeyIsBlocked`) → run ends `needs_manual_action` (operator must rotate the configured key), NOT a generic failure.
- **2GIS bot wall / access challenge on the proxy HTML fetch** → `needs_manual_action` with a saved HTML debug artifact; no captcha bypass (constitution IV).
- **Org has zero reviews** → run completes successfully with zero inserted.
- **Reaching the configured `limit`** stops pagination early.
- **Malformed review object** (missing rating/text) → that review degrades safely (rating defaults, empty text) rather than crashing the run.
- **Direct API IP-blocked in production** → the scraper retries the same request through the ScrapeOps proxy (fallback), and only fails if the proxy path also fails.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST add a new scrape mode `twogis_api` to `ScrapeMode`, selectable per-organization and via `/scrape/all`, without removing or altering existing modes.
- **FR-002**: System MUST provide a `TwogisApiScraper` that, given a 2GIS org URL, resolves a `firm_id`, resolves that to an `org_id` and org metadata via the 2GIS catalog API, and fetches org-level reviews via the 2GIS reviews API with pagination bounded by a configurable `limit` and page size.
- **FR-003**: The scraper MUST take `firm_id` from a full `…/firm/{id}` URL without any network call; for short links (`go.2gis.com/CODE`) it MUST resolve the firm id via the ScrapeOps proxy (direct SPA fetch is bot-walled).
- **FR-004**: The scraper MUST map each 2GIS review JSON object to the standard `ParsedReview` (`author_name`←`user.name`, `rating`, `review_text`←`text`, `review_date_text`←`date_created`, `response_text`←`official_answer.text`, `external_review_id`←`id`) and return the standard `ScrapeResult`.
- **FR-005**: 2GIS scrapes MUST persist through the existing `ReviewService.upsert_reviews` path so dedup (`content_hash`) and analytics (feature 002) apply unchanged, tagging reviews `scrape_mode=twogis_api`. The 2GIS mapping MUST NOT change `build_review_hash` inputs or normalization.
- **FR-006**: Every 2GIS scrape MUST produce a `ScrapeRun` with status, timestamps, and counts, consistent with other modes. Failures MUST record an `error_code`/`error_message`; access challenges and blocked keys MUST surface as `needs_manual_action`, not generic failures.
- **FR-007**: The existing scrape trigger endpoint MUST accept `mode=twogis_api` (no new endpoint); background-task execution and `ScrapeRun` polling are reused.
- **FR-008**: 2GIS parameters (catalog key, review key, `limit`, page size, request delay) MUST be configurable via settings with sensible defaults; the public 2GIS catalog and reviews keys ship as defaults.
- **FR-009**: The direct 2GIS API path MUST fall back to the ScrapeOps proxy on IP-block (403/network), reusing the existing `SCRAPEOPS_API_KEY`; credentials MUST NOT leak into `error_message` or logs.
- **FR-010**: A new Alembic migration MUST add `twogis_api` to the Postgres `scrape_mode_enum` (mirroring migration 0003 for `scrapeops`); SQLite test backends rely on the ORM enum only.

### Key Entities *(include if feature involves data)*

- **ScrapeMode.twogis_api**: New enum value; no new tables. Reuses `ScrapeRun` and `Review` exactly as existing modes do. `Review.scrape_mode` records provenance.
- **Organization.yandex_url**: Reused as the generic org URL; for 2GIS orgs it holds the 2GIS URL. (Renaming the column is out of scope for this feature.)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running a `twogis_api` scrape against fixture API responses stores reviews tagged `scrape_mode=twogis_api` and records a successful `ScrapeRun` with non-zero counts.
- **SC-002**: A second identical 2GIS scrape inserts 0 new reviews (all deduplicated by `content_hash`).
- **SC-003**: A blocked catalog key yields a `needs_manual_action` run (not `failed`), with 0 unhandled exceptions.
- **SC-004**: The existing Yandex modes continue to work unchanged (existing tests stay green), and no 2GIS branching touches `build_review_hash`.
- **SC-005**: A full `…/firm/{id}` URL collects reviews with no ScrapeOps call; a `go.2gis.com/CODE` short link collects the same org's reviews via one proxy resolution.

## Assumptions

- The public 2GIS catalog key (`rubnkm7490`) and reviews key (`6e7e1929-…`) embedded in the 2GIS web client remain usable; they are configurable so a block can be resolved by rotating the setting, and a blocked key surfaces as `needs_manual_action`.
- 2GIS reviews are collected at **org level**; branch-level filtering is out of scope for this feature.
- `date_created` is immutable per review, so using it as `review_date_text` keeps `content_hash` stable across re-scrapes.
- The org's 2GIS URL is stored on the existing `Organization` record; no organization auto-creation in this feature.
- Frontend surfacing of the mode (a selector/page) is out of scope here — the mode is usable via the existing scrape trigger API; a dedicated UI can follow.
