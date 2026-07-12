# Feature Specification: Backend Hardening — Scrape Reliability, Performance, Data Consistency

**Feature Branch**: `010-backend-hardening`

**Created**: 2026-07-12

**Status**: Draft

**Input**: User description: "Backend hardening: fix critical scrape/persistence bugs, N+1 performance issues, and data-consistency gaps found in audit (12 items: batch-safe review persistence with accurate counters; aggregated parent run status for bulk scrape; non-blocking session login/check; auth-scraper challenge re-check with debug artifacts; removal of per-review and per-org N+1 query patterns; review query indexes; uniform minimum-rating guard across providers; shared bot-detection markers; application logging for swallowed errors; fail-closed CORS configuration)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reviews are never lost during overlapping scrapes (Priority: P1)

An operator triggers a bulk scrape while a single-organization scrape of the same organization is still running. Today a collision between the two runs can silently discard reviews that were already collected in the same batch, while the run report still counts them as inserted. After this change, every collected review is persisted exactly once and the run counters (`seen / inserted / updated`) match what is actually in the database.

**Why this priority**: Silent data loss is the worst possible failure for a collection tool — the dashboard's purpose is completeness. Wrong counters also destroy trust in every other run report.

**Independent Test**: Simulate two concurrent persistence batches for the same organization containing overlapping reviews; verify no previously-inserted review disappears, no duplicates appear, and reported counters equal actual row changes.

**Acceptance Scenarios**:

1. **Given** a batch of new reviews being persisted, **When** one review collides with a concurrently-inserted duplicate, **Then** all other reviews in the batch remain persisted and the colliding review is treated as an update.
2. **Given** any completed scrape run, **When** its counters are compared to actual database changes, **Then** `reviews_inserted` and `reviews_updated` are exact.
3. **Given** a re-scrape of an unchanged organization, **When** persistence completes, **Then** no new rows are created (dedup contract unchanged).

---

### User Story 2 - Bulk scrape reports its true outcome (Priority: P1)

An operator runs "scrape all" overnight. Every organization hits a bot-protection wall. Today the parent run still says `success` with zero counts. After this change, the parent run status reflects the aggregate of its children, and its counters roll up child totals, so the operator sees at a glance that the network scrape actually needs attention.

**Why this priority**: A falsely green bulk run hides network-wide failures — the exact situation the operator most needs to notice (constitution: scraper debuggability).

**Independent Test**: Create a parent run with children in various terminal states; verify the parent's status and counters follow the aggregation rules.

**Acceptance Scenarios**:

1. **Given** a bulk scrape where all children failed, **When** the parent run completes, **Then** its status is `failed`.
2. **Given** a bulk scrape where at least one child ended as `needs_manual_action` and none succeeded, **When** the parent completes, **Then** its status is `needs_manual_action`.
3. **Given** a bulk scrape with mixed outcomes including at least one success, **When** the parent completes, **Then** its status conveys partial success (success with rolled-up counters; child statuses remain individually visible).
4. **Given** any completed bulk run, **When** the parent is inspected, **Then** `reviews_seen/inserted/updated` equal the sums over its children.

---

### User Story 3 - Session login and check do not freeze the API (Priority: P2)

An operator starts a Yandex operator-session login or session check. Today the API blocks for tens of seconds while a browser runs, despite responding with "accepted". After this change the endpoint returns immediately and the operator polls session status to see the result, consistent with how scrape runs already behave.

**Why this priority**: Blocking requests tie up the API and mislead API consumers about when work happens; but no data is lost, so lower than P1.

**Independent Test**: Call login/check endpoints and verify they return promptly with the work scheduled; poll session status until it reaches a terminal state.

**Acceptance Scenarios**:

1. **Given** a login request, **When** the endpoint responds, **Then** the response is immediate ("accepted") and the browser work runs in the background.
2. **Given** a background login/check in progress, **When** the operator polls session status, **Then** they can observe the pending state and the eventual outcome (valid / needs manual action / error).

---

### User Story 4 - Operator-auth scrape detects late challenges like the public scrape (Priority: P2)

During an operator-auth scrape, a captcha appears only after navigating to the reviews tab. Today that challenge page is parsed as if it contained reviews, and no debug artifacts are saved. After this change, the auth scrape applies the same challenge checks at the same navigation points as the public scrape, ends the run as `needs_manual_action`, and saves debug artifacts.

**Why this priority**: Produces garbage-in data and violates the debuggability rule, but occurs only in the operator-auth mode.

**Independent Test**: Simulate a challenge page appearing after reviews navigation in auth mode; verify run status `needs_manual_action` and saved artifacts.

**Acceptance Scenarios**:

1. **Given** an auth scrape where the challenge appears after reviews navigation, **When** the scrape proceeds, **Then** the run ends `needs_manual_action` (never parsed as reviews) with debug artifacts saved.

---

### User Story 5 - Dashboard and lists stay fast as data grows (Priority: P2)

An operator with dozens of organizations and thousands of reviews opens the network overview, the companies list, and review lists. Today each of these issues a query per organization / per review / per company (N+1 patterns) and review sorting has no index support. After this change, the same screens produce a bounded number of queries and indexed review scans.

**Why this priority**: Current scale masks it, but query counts grow multiplicatively with organizations × platforms; fixing now is cheap.

**Independent Test**: Count queries issued by review persistence, overview aggregation, and companies list for a fixed dataset; verify bounded counts and unchanged responses.

**Acceptance Scenarios**:

1. **Given** a persistence batch of N reviews, **When** it runs, **Then** existing-review lookup uses a constant number of queries, not N.
2. **Given** the network overview for N organizations, **When** it is computed, **Then** rating-delta and platform aggregation do not issue per-organization redundant queries and do not re-scan reviews already loaded.
3. **Given** the companies list, **When** it renders branch counts, **Then** counts come from a single grouped query.
4. **Given** the reviews table, **When** reviews are listed or filtered by date/platform, **Then** the queries are index-supported.
5. **Given** all of the above, **When** API responses are compared before/after, **Then** payloads are identical.

---

### User Story 6 - Consistent data rules and visible errors (Priority: P3)

Reviews from any provider follow the same validity rules (no zero-rating reviews polluting rating math); bot-detection markers are defined once so providers cannot drift apart; swallowed background errors appear in application logs; and a misconfigured CORS origin list fails loudly at startup instead of silently widening to all origins.

**Why this priority**: Correctness and operability polish — real value, no acute data loss.

**Independent Test**: Feed a zero-rating 2GIS review through mapping (dropped); inspect shared marker module usage; trigger a snapshot failure and observe a log line; start the app with empty CORS origins and observe an explicit configuration error.

**Acceptance Scenarios**:

1. **Given** a 2GIS review with missing/unparseable rating, **When** it is mapped, **Then** it is excluded exactly as the Yandex parser excludes sub-1 ratings.
2. **Given** the three Yandex scrapers, **When** their bot/captcha markers are inspected, **Then** they import one shared definition.
3. **Given** a background snapshot save that raises, **When** it is caught, **Then** a warning with context is logged (no silent bare except).
4. **Given** an empty CORS origins setting, **When** the API starts, **Then** startup fails with an explicit configuration error rather than serving `*` with credentials.

### Edge Cases

- Concurrent duplicate insert arrives between the preloaded-hash check and the insert itself → must still resolve to an update, not a lost batch.
- Bulk scrape with zero organizations → parent run completes with a defined status (success, zero counters).
- Child run crashes before reaching a terminal status → parent aggregation must not hang; treat as failed.
- Login requested while a previous background login is still running → second request must not corrupt session state (reject or supersede, deterministically).
- Reviews with legitimately missing rating from 2GIS → excluded from persistence, counted in `reviews_seen` only.
- Existing databases: new indexes must apply via migration without locking concerns at current scale; SQLite test backend must tolerate the same schema.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Review persistence MUST survive a mid-batch uniqueness collision without discarding any other review in the batch, and MUST resolve the colliding review as an update.
- **FR-002**: Scrape run counters (`reviews_seen`, `reviews_inserted`, `reviews_updated`) MUST exactly reflect actual database effects of that run.
- **FR-003**: Review persistence MUST NOT issue one existing-review lookup query per review; lookups MUST be batched.
- **FR-004**: The parent run of a bulk scrape MUST derive its terminal status from child outcomes: all failed → `failed`; no success and ≥1 `needs_manual_action` → `needs_manual_action`; ≥1 success → `success`. Parent counters MUST be sums of child counters.
- **FR-005**: Session login and session check operations MUST return immediately and execute browser work asynchronously; session status MUST be observable by polling and MUST expose pending and terminal states.
- **FR-006**: The operator-auth scraper MUST re-check for access challenges after navigating to the reviews view (same checkpoints as the public scraper) and MUST save debug artifacts when a challenge is detected, ending the run as `needs_manual_action`.
- **FR-007**: Network overview computation MUST NOT re-fetch organizations already in memory, MUST batch-load rating snapshots for all organizations/platforms in the period, and MUST reuse already-loaded reviews for platform aggregation.
- **FR-008**: The companies list MUST compute branch counts with a single grouped query.
- **FR-009**: Review storage MUST have index support for (organization, review date) ordering and (organization, first-seen) / (organization, platform) filtering, delivered as a schema migration compatible with both Postgres and the SQLite test backend.
- **FR-010**: Reviews with rating below 1 MUST be excluded from persistence uniformly across all providers (2GIS aligned with Yandex behavior).
- **FR-011**: Bot-protection/captcha markers MUST be defined in one shared module and imported by all Yandex scrapers; 2GIS keeps its superset but reuses the shared base.
- **FR-012**: The application MUST have a logging setup; every caught-and-suppressed exception on scrape/snapshot paths MUST emit at least a warning with organization/run context. Credentials and storage-state contents MUST never be logged.
- **FR-013**: API startup MUST fail with an explicit configuration error when the CORS origin list is empty, instead of defaulting to all origins while credentials are allowed.
- **FR-014**: The deduplication contract (hash inputs, normalization, update-not-insert on re-scrape) MUST remain byte-for-byte unchanged; all existing tests MUST keep passing.

### Key Entities

- **Review**: stored review; gains index support, no schema field changes.
- **ScrapeRun**: gains correct aggregate semantics for parent (bulk) runs; counter fields now guaranteed-accurate.
- **ScraperSession**: gains an observable pending state while background login/check is executing.
- **RatingSnapshot**: unchanged shape; now batch-loaded for overview computation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under concurrent overlapping scrapes of the same organization, zero reviews are lost and zero duplicates are created (verified by automated concurrency test).
- **SC-002**: 100% of bulk scrape parent runs report a status consistent with their children and counters equal to child sums.
- **SC-003**: Session login/check endpoints respond in under 1 second regardless of browser work duration.
- **SC-004**: For a fixed dataset of N organizations and M reviews, the number of queries for review persistence and network overview is bounded by a constant (does not grow with N or M).
- **SC-005**: All pre-existing tests pass unchanged; new tests cover each fixed defect (concurrency-safe upsert, parent aggregation, async session ops, challenge re-check, zero-rating exclusion, CORS fail-closed).
- **SC-006**: A deliberately-triggered snapshot failure produces a visible warning log entry with run context.

## Assumptions

- Bulk-scrape partial success maps to parent status `success` (with per-child detail preserved) — no new enum value is introduced.
- "Immediate" for login/check means the endpoint schedules background work exactly like scrape endpoints already do; no new job infrastructure (no Celery — constitution YAGNI).
- Index migration is additive-only; no table rewrites; safe at current data volume.
- CORS fail-closed applies at startup only when credentials mode is enabled (current configuration); `.env.example` documents a valid default origin list so local setups keep working.
- Zero-rating 2GIS reviews are considered invalid data, not a distinct rating class; excluding them matches existing Yandex semantics and does not require backfill deletion of previously-stored rating-0 rows (a one-time cleanup is out of scope unless requested).
- No frontend changes are in scope; API response shapes stay identical.
