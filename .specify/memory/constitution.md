<!--
Sync Impact Report
Version change: 1.4.0 → 1.5.0
Modified principles:
  - VII. Admin Panel Security → Admin Panel Security & Configurable RBAC — the fixed
    two-role model (admin/review_operator) is replaced by an admin-managed configurable
    role system: a `roles` table + `role_permissions` grant matrix + `users.role_id` FK.
    Backend is the enforcement source of truth (a `require_permission` dependency, 403 on
    deny); the frontend mirrors permissions from `/api/auth/me` for UX only. `admin` is an
    immutable `is_system` role with full access that cannot be deleted or downgraded.
    Both page-level and action-level permissions are in scope. Single shared auth system
    preserved (users/bcrypt/ADMIN_SECRET_KEY session cookie) — no second auth system.
  - III. Critical-Path Testing — "role-based access per view" generalized to
    "permission-based access per page and per action"; role CRUD guards must be tested.
Added sections:
  - MVP Scope Boundaries — configurable roles/permissions (feature 016) added to in-scope.
Modified sections: None (dedup contract build_review_hash / uq_review_org_hash unchanged;
  Read-Only Principle II unchanged — posting replies stays out of scope)
Removed sections: None
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check section aligns (no changes needed)
  ✅ .specify/templates/spec-template.md — scope alignment verified (no changes needed)
  ✅ .specify/templates/tasks-template.md — task categorization aligns (no changes needed)
Follow-up TODOs: Feature 016 (roles-permissions) spec/plan to cite Principles III & VII.

Prior report (1.3.0 → 1.4.0):
  - I. MVP Scope Discipline — custom Next.js control panel + Company parent entity added.
  - VII. Admin Panel Security — extended to cover a custom Next.js control panel reusing
    the feature-004 auth; no second auth system.
-->

# ReviewsDashboard Constitution

## Core Principles

### I. MVP Scope Discipline

Every deliverable MUST stay within the documented MVP in/out-of-scope list. Features
explicitly excluded — review replies, Google Maps, LLM/external-ML analysis,
WebSocket/email notifications, Celery pipelines, anti-captcha bypass — MUST NOT be
introduced without a constitution amendment and spec update. Deterministic, rule-based
local analytics over already-collected reviews (see Principle VI) are in scope and do
NOT count as excluded "LLM analysis". The internal admin panel with RBAC (see
Principle VII) is in scope as of v1.2.0. 2GIS review collection via its public reviews
API (see Principle VIII) is in scope as of v1.3.0; Google Maps remains excluded. A custom
authenticated Next.js control panel (login + admin cabinet + Company/Branch management)
and a `Company` additive parent entity above organizations (see Principle VII) are in
scope as of v1.4.0. An admin-managed configurable role/permission system (custom roles +
page/action permission matrix, see Principle VII) is in scope as of v1.5.0.

**Rationale**: The product is an internal read-only review collector; scope creep delays
the first working vertical slice.

### II. Read-Only Review Collection

The system MUST collect and display reviews from supported providers (Yandex Maps and
2GIS) only. It MUST NOT publish, edit, or delete replies on any provider. Visible
business responses (e.g. official answers) MAY be stored when present in the scraped
page or provider API, but the product MUST NOT act as a reply management tool.

**Rationale**: Reply workflows, moderation, and platform ToS risks are out of MVP scope.

### III. Critical-Path Testing

Business-critical logic MUST have automated tests before merge: review deduplication,
review content normalization/hash generation, organization and scrape-run API contracts,
and scraper result persistence. UI smoke tests SHOULD cover the primary dashboard flows.
RBAC rules MUST be covered by automated tests: auth success/failure, permission-based
access per page and per action (allow/deny/403), and role-management guards (a system role
cannot be deleted or downgraded; a role bound to users cannot be deleted). Full TDD for
every file is NOT required; tests MUST cover logic that would cause data loss, duplicate
reviews, silent scrape failures, or RBAC bypasses.

**Rationale**: Duplicate reviews, lost scrape results, and RBAC bypasses are the
highest-impact failure modes for this product.

### IV. Scraper Reliability & Debuggability

Every scrape attempt MUST produce a scrape-run record with status, timestamps, counts,
and error details. Failed runs MUST save debug artifacts (screenshot and HTML snapshot
paths). Captcha, 2FA, or access challenges MUST surface as `needs_manual_action`, not
as generic failures or silent retries.

**Rationale**: Scraping is inherently fragile; operators need actionable failure signals.

### V. Simplicity (YAGNI)

Prefer the simplest architecture that satisfies the spec: FastAPI background tasks instead
of Celery, monorepo with `apps/api` and `apps/web`, Docker Compose for local development.
Additional services, queues, or abstractions MUST be justified in the plan's Complexity
Tracking table. The admin panel uses sqladmin as a sub-app mounted on the existing FastAPI
instance — no separate service.

**Rationale**: MVP velocity and operability beat premature scaling infrastructure.

### VI. Deterministic Local Analytics

Analytics over collected reviews — sentiment classification, problem/complaint
categorization, rating↔sentiment mismatch flags — MUST be deterministic and computed
locally from rule-based dictionaries and regular expressions. They MUST NOT call out to
LLMs, hosted ML services, or any external inference API, and MUST degrade safely
(produce a neutral/empty result, never raise) on missing or malformed text. Analytics
are display/insight aids derived from stored reviews; they MUST NOT mutate the raw
scraped review text, rating, or dedup hash inputs.

**Rationale**: Rule-based analytics give operators actionable insight with no new
infrastructure, no per-call cost, and no platform/ToS risk.

### VII. Admin Panel Security & Configurable RBAC

The internal admin panel (sqladmin, mounted at `/admin`) MUST enforce authentication
before any view is accessible. Passwords MUST be stored only as bcrypt hashes; plaintext
passwords MUST NOT appear in code, logs, or API responses. The session secret key MUST
come from an environment variable (`ADMIN_SECRET_KEY`) and MUST NOT be hardcoded. The
sqladmin panel's own view-layer RBAC (`is_accessible`/`can_create`/`can_edit`/`can_delete`)
gates on whether the signed-in user holds the `admin` role. The admin panel is additive:
it MUST NOT modify existing API routes, scraper logic, or ORM models beyond additive
column additions. The application MUST start cleanly after each implementation phase.

**Configurable roles & permissions (v1.5.0).** Roles are no longer a fixed two-value
enum. They live in a `roles` table (admin-managed) with a `role_permissions` grant matrix
and a `users.role_id` foreign key. Two permission granularities are defined and both are
in scope: **page** permissions (access to a control-panel page) and **action**
permissions (performing a specific operation, e.g. running a scrape or editing a review's
status). Posting/editing replies on any provider remains out of scope (Principle II) and
MUST NOT be introduced as an action permission. The following invariants are
NON-NEGOTIABLE:

- **Backend is the source of truth.** Every protected route MUST be guarded by a
  server-side permission dependency (`require_permission(<permission>)`) that returns 403
  on deny and 401 when unauthenticated. The frontend MAY hide navigation items, buttons,
  and other UI elements it lacks permission for, but this is UX only and MUST NOT be the
  sole enforcement — the API MUST reject the request regardless of what the UI shows.
- **`admin` is immutable.** A single `is_system` role named `admin` always resolves to
  full access, and MUST NOT be deletable, renamable, or have any permission revoked.
  A role bound to one or more users MUST NOT be deletable.
- **One shared auth system.** Roles reuse the existing `users` table, bcrypt hashes, and
  the `ADMIN_SECRET_KEY`-signed session cookie. Introducing a second auth system (e.g. a
  parallel JWT identity store) is FORBIDDEN. `/api/auth/me` MUST expose the caller's role
  and effective permission set so the frontend can mirror access decisions.
- **Additive & dedup-frozen.** ORM changes stay additive-only; the reviews deduplication
  contract (`build_review_hash`, `uq_review_org_hash`) MUST remain unchanged —
  `organizations` stays the scrape/dedup unit.

**Rationale**: The panel exposes all collected data and scrape controls; authentication
and server-enforced permissions protect it from unauthorized access in a shared internal
environment. A configurable matrix lets a small operator team shape access (admin, call
center, manager, …) without code changes, while an immutable `admin` role and a single
auth system keep the system recoverable and low-risk.

### VIII. Multi-Provider Collection

Provider integrations MUST reuse the existing collection contract: each provider scraper
returns the standard `ScrapeResult` (organization + reviews) and persists through
`ReviewService.upsert_reviews`, so deduplication (`content_hash`), normalization, and
analytics (Principle VI) apply unchanged across providers. A provider is selected by an
explicit `ScrapeMode` value; no provider-specific branching may leak into the dedup hash
inputs. Provider access MUST stay read-only (Principle II) and prefer official/public
data endpoints over brittle HTML scraping where one exists. Provider API keys and proxy
credentials MUST live in settings/environment, never hardcoded in a way that leaks into
logs or API responses (see Security & Credentials). Adding a provider is an amendment +
spec, not an ad-hoc change.

**Rationale**: The 2GIS reviews API and Yandex share the same review shape; a single
persistence/dedup path keeps multi-provider collection consistent and low-risk.

## MVP Scope Boundaries

**In scope**: Yandex Maps organization tracking, public and operator-auth scraping,
review display, manual scrape triggers (single and bulk), scrape history, deduplication,
debug artifacts for failures, structured (BeautifulSoup) review parsing with date
normalization, deterministic rule-based review analytics (sentiment, problem
categorization, rating↔sentiment mismatch) per Principle VI, an internal admin
panel with authentication and role-based access control (admin + review_operator) per
Principle VII, 2GIS review collection via its public reviews API (catalog + reviews
endpoints) per Principle VIII, a `Company` additive parent entity grouping organizations
(branches) by city, and a custom authenticated Next.js control panel (login + admin
cabinet + Company/Branch CRUD) reusing the Principle VII auth per v1.4.0. An admin-managed
configurable role/permission system (custom roles, page + action permission matrix,
`/settings/roles` management UI, `require_permission` backend enforcement) per Principle
VII is in scope as of v1.5.0.

**Out of scope**: Posting replies (including as an action permission), Google Maps and
other map providers (except Yandex and 2GIS), LLM/external-ML analysis, real-time
notifications, TimescaleDB, forced captcha bypass, a second/parallel authentication
system, per-organization/per-record row-level permissions, and changes to the review
deduplication contract.

**Scale assumption**: Internal tool for a small operator team tracking on the order of
tens of organizations, not thousands of concurrent users.

## Security & Credentials

Operator Yandex credentials MUST live in environment variables only. Playwright storage
state files MUST NOT be committed to version control. Passwords, cookies, and storage
state contents MUST NOT appear in logs or API responses. The `.local/` directory MUST
be gitignored.

Admin panel session secret (`ADMIN_SECRET_KEY`) MUST be set via environment variable.
Initial user passwords MUST be supplied via environment variables or CLI arguments to
seed scripts — never hardcoded. Password hashes MUST use bcrypt (via `passlib[bcrypt]`).

## Development Workflow

Features follow Spec Kit: constitution → specify → plan → tasks → implement. The
implementation plan in `specs/<feature>/plan.md` is the source of truth for tech stack
and structure. Agent context in `.cursor/rules/specify-rules.mdc` MUST reference the
active plan path between `<!-- SPECKIT START -->` and `<!-- SPECKIT END -->` markers.

Delivery milestones (data backbone → public scraper → dashboard → operator auth) SHOULD
be completed in order; each milestone MUST be independently verifiable per `quickstart.md`.

## Governance

This constitution supersedes ad-hoc implementation choices. Amendments require:

1. Updating `.specify/memory/constitution.md` with a semantic version bump.
2. Propagating changes to affected templates and the active feature spec/plan if scope
   or principles change materially.
3. Documenting rationale in the Sync Impact Report HTML comment at the top of the
   constitution file.

Compliance review: every plan MUST include a Constitution Check gate; violations MUST be
documented in Complexity Tracking with rejected simpler alternatives.

**Version**: 1.5.0 | **Ratified**: 2026-06-14 | **Last Amended**: 2026-07-22
