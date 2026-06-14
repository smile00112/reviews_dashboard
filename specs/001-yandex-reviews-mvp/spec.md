# Feature Specification: Yandex Reviews MVP

**Feature Branch**: `001-yandex-reviews-mvp`

**Created**: 2026-06-14

**Status**: Draft

**Input**: User description: "Урезанный MVP для работы с отзывами Яндекс Карт — внутренний дашборд для сбора и отображения отзывов организаций Яндекс Карт без auth, ролей и ответов на отзывы."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Organization Board (Priority: P1)

As an internal operator, I want to add Yandex Maps organization URLs and see a board
listing each organization with its scrape status and last successful update, so I can
track which locations we monitor.

**Why this priority**: Without tracked organizations there is nothing to scrape or
display; this is the entry point for all other workflows.

**Independent Test**: Add at least one valid Yandex Maps URL, confirm it appears on the
board with status `pending`, preferred scrape mode, and empty or placeholder metadata
until the first scrape completes.

**Acceptance Scenarios**:

1. **Given** an empty organization list, **When** the operator submits a valid Yandex
   Maps organization URL, **Then** the organization appears on the board with status
   `pending` and the chosen preferred scrape mode.
2. **Given** organizations on the board, **When** the operator views the list, **Then**
   each row shows name (or URL fallback), rating, review count when known, preferred
   mode, last scrape status, and last successful scrape timestamp.
3. **Given** an organization on the board, **When** the operator changes preferred
   scrape mode or display name, **Then** the update is persisted and reflected on the
   board.
4. **Given** an organization on the board, **When** the operator removes it, **Then** it
   no longer appears in the organization list.

---

### User Story 2 - Public Review Collection (Priority: P1)

As an internal operator, I want to manually trigger a public scrape for one organization
and see collected reviews on its detail page, so I can monitor customer feedback without
logging into Yandex.

**Why this priority**: Public scraping is the core value delivery — collecting reviews
without operator credentials is the simplest working vertical slice.

**Independent Test**: Add an organization, click update in public mode, wait for scrape
completion, open the organization detail page and confirm reviews are listed. Run scrape
again and confirm no duplicate reviews appear.

**Acceptance Scenarios**:

1. **Given** a tracked organization with preferred mode `public`, **When** the operator
   clicks update for that organization, **Then** a scrape run starts, transitions
   through running to success or failed, and the organization row reflects the outcome.
2. **Given** a successful public scrape, **When** the operator opens the organization
   detail page, **Then** reviews show author, rating, date, text, and scrape mode.
3. **Given** reviews already stored for an organization, **When** the operator runs
   public scrape again, **Then** existing reviews are not duplicated and new reviews
   are added.
4. **Given** a scrape that encounters captcha or access challenge, **When** the run
   finishes, **Then** status is `needs_manual_action` with a readable error message.

---

### User Story 3 - Global Reviews Feed (Priority: P2)

As an internal operator, I want a single page showing reviews from all tracked
organizations with filters, so I can scan recent feedback across locations without
opening each organization separately.

**Why this priority**: Cross-organization visibility is high value once collection works,
but depends on organizations and at least one successful scrape.

**Independent Test**: With reviews from two or more organizations, open the global feed,
filter by organization and rating, and confirm only matching reviews appear.

**Acceptance Scenarios**:

1. **Given** reviews exist for multiple organizations, **When** the operator opens the
   global reviews page, **Then** reviews from all organizations are listed sorted by
   date (newest first).
2. **Given** the global reviews page, **When** the operator applies filters for
   organization, rating, date range, or new-only, **Then** only matching reviews are
   shown.
3. **Given** no reviews have been collected yet, **When** the operator opens the global
   reviews page, **Then** an empty state message is displayed.

---

### User Story 4 - Scrape History & Failure Debugging (Priority: P2)

As an internal operator, I want to see scrape run history with status, counts, errors,
and links to debug artifacts for failed runs, so I can diagnose scraping problems.

**Why this priority**: Scraping fails often; operators need visibility without reading
server logs.

**Independent Test**: Trigger a failed scrape (e.g., invalid URL), open scrape history,
confirm error message and debug artifact paths are visible and `needs_manual_action`
is visually distinct.

**Acceptance Scenarios**:

1. **Given** scrape runs have occurred, **When** the operator opens scrape history,
   **Then** each run shows mode, status, start time, duration, reviews seen/inserted
   counts, and error message when failed.
2. **Given** a failed scrape run, **When** the operator views run details, **Then**
   paths or links to screenshot and HTML snapshot debug artifacts are shown.
3. **Given** a bulk scrape for all organizations, **When** the operator views history,
   **Then** parent and per-organization runs are distinguishable.

---

### User Story 5 - Operator-Authenticated Scraping (Priority: P3)

As an internal operator, I want to configure Yandex operator credentials, save an
authenticated browser session, and scrape in operator-auth mode when public scraping
is insufficient, so I can collect reviews that require login.

**Why this priority**: Auth mode adds operational complexity (credentials, session
expiry, captcha); it extends but does not replace the public scrape path.

**Independent Test**: Configure credentials, run login flow, confirm session status is
`valid`, scrape one organization in operator-auth mode, confirm reviews are stored with
that scrape mode.

**Acceptance Scenarios**:

1. **Given** operator credentials in environment configuration, **When** the operator
   initiates Yandex login, **Then** a Playwright session is saved and session status
   API returns `valid` without exposing secrets.
2. **Given** a valid saved session, **When** the operator triggers operator-auth scrape
   for an organization, **Then** reviews are collected and marked with operator-auth
   scrape mode.
3. **Given** an expired session or login requiring captcha/2FA, **When** login or scrape
   is attempted, **Then** status becomes `needs_manual_action` with guidance to resolve
   manually.
4. **Given** any API response, **When** session status is queried, **Then** passwords,
   cookies, and storage state contents are never returned.

---

### Edge Cases

- What happens when the user submits an invalid or non-Yandex URL? System rejects with a
  clear validation error; no organization is created.
- What happens when the same review text appears with different whitespace? Deduplication
  treats normalized content as identical; review is not inserted twice.
- What happens when Yandex page structure changes mid-scrape? Run fails with error
  message and debug artifacts; organization status reflects failure.
- What happens when operator triggers "update all" while a scrape is already running?
  New runs are queued or rejected with clear feedback; no silent overlap without status
  tracking.
- What happens when organization has zero reviews on Yandex? Scrape succeeds with zero
  inserts; detail page shows empty state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow operators to add organizations by Yandex Maps URL.
- **FR-002**: System MUST validate that submitted URLs are Yandex Maps organization URLs.
- **FR-003**: System MUST display an organization board with scrape status and last
  successful scrape timestamp for each tracked organization.
- **FR-004**: System MUST allow operators to set preferred scrape mode per organization
  (`public` or `operator_auth`).
- **FR-005**: System MUST allow manual scrape trigger for a single organization.
- **FR-006**: System MUST allow manual scrape trigger for all organizations at once.
- **FR-007**: System MUST collect reviews from Yandex Maps organization pages via
  automated browser scraping in public mode without operator login.
- **FR-008**: System MUST collect reviews via operator-authenticated scraping when
  session is valid and mode is `operator_auth`.
- **FR-009**: System MUST deduplicate reviews per organization using stable content
  identity so the same review is never stored twice.
- **FR-010**: System MUST record every scrape attempt with status, timestamps, review
  counts, and error details.
- **FR-011**: System MUST save screenshot and HTML snapshot references for failed scrape
  runs to aid debugging.
- **FR-012**: System MUST display organization detail page with paginated reviews.
- **FR-013**: System MUST provide a global reviews feed with filters by organization,
  rating, date range, and new-only.
- **FR-014**: System MUST display scrape run history with failure details and debug
  artifact references.
- **FR-015**: System MUST support Yandex operator login flow saving authenticated
  session state locally.
- **FR-016**: System MUST expose session status without revealing credentials or cookies.
- **FR-017**: System MUST NOT require application-level login or role management.
- **FR-018**: System MUST NOT publish, edit, or delete replies on Yandex Maps.
- **FR-019**: System MUST surface captcha, 2FA, and access challenges as
  `needs_manual_action` rather than attempting forced bypass.

### Key Entities

- **Organization**: A Yandex Maps location being monitored; holds URL, metadata
  (name, address, rating, review count), preferred scrape mode, and last scrape status.
- **Review**: A collected customer review linked to one organization; includes author,
  rating, text, dates, optional visible business response, scrape mode, and deduplication
  identity.
- **Scrape Run**: One execution attempt to collect reviews; tracks mode, status,
  timing, counts, errors, and debug artifact paths. May represent single-organization
  or bulk-all run.
- **Scraper Session**: Metadata for operator Yandex authentication state; tracks validity,
  last login, and storage location without exposing secrets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator can add at least 5 Yandex Maps organization URLs and see all on
  the organization board within one session.
- **SC-002**: Operator can run public scrape for one organization and view collected
  reviews on the detail page within 5 minutes of triggering (excluding Yandex-side delays).
- **SC-003**: Re-running scrape on the same organization does not increase duplicate
  review count — 100% of identical reviews are deduplicated.
- **SC-004**: Every scrape attempt produces a visible run record with final status and
  timing; failed runs include accessible debug artifact references.
- **SC-005**: Operator can identify last successful scrape time for any organization
  from the board without opening detail pages.
- **SC-006**: Operator-auth scrape successfully collects reviews for at least one
  organization when valid credentials and session are configured.
- **SC-007**: Session and credential data never appear in UI or API responses intended
  for routine operator use.

## Assumptions

- Single internal operator team uses the dashboard on trusted networks; no multi-tenant
  or public internet exposure is required for MVP.
- Operator has legitimate Yandex account credentials when using operator-auth mode.
- Yandex Maps public organization pages remain accessible for scraping without login
  for most organizations in public mode.
- MVP targets tens of organizations, not thousands; bulk scrape runs sequentially or
  with modest concurrency is acceptable.
- Russian-language review content is primary; text normalization preserves Cyrillic.
- Hard delete of organizations is acceptable for MVP (no compliance-driven soft-delete).
- Application runs locally or on internal infrastructure via Docker Compose.
