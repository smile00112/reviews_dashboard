<!--
Sync Impact Report
Version change: 1.2.0 → 1.3.0
Modified principles:
  - I. MVP Scope Discipline — 2GIS removed from the excluded list; now an in-scope provider
  - II. Read-Only Review Collection — broadened from "Yandex only" to "Yandex and 2GIS"
Added sections:
  - Principle VIII. Multi-Provider Collection (new principle)
Modified sections:
  - MVP Scope Boundaries — added "2GIS review collection via public reviews API"
    to in-scope; "other map providers" narrowed to exclude only Google (2GIS now allowed)
Removed sections: None
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check section aligns (no changes needed)
  ✅ .specify/templates/spec-template.md — scope alignment verified (no changes needed)
  ✅ .specify/templates/tasks-template.md — task categorization aligns (no changes needed)
Follow-up TODOs: Feature 006 (2gis reviews) spec/plan to cite Principle VIII.
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
API (see Principle VIII) is in scope as of v1.3.0; Google Maps remains excluded.

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
Admin panel RBAC rules MUST be covered by automated tests (auth success/failure,
role-based access per view). Full TDD for every file is NOT required; tests MUST cover
logic that would cause data loss, duplicate reviews, or silent scrape failures.

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

### VII. Admin Panel Security

The internal admin panel (sqladmin, mounted at `/admin`) MUST enforce authentication
before any view is accessible. Passwords MUST be stored only as bcrypt hashes; plaintext
passwords MUST NOT appear in code, logs, or API responses. The session secret key MUST
come from an environment variable (`ADMIN_SECRET_KEY`) and MUST NOT be hardcoded.
RBAC MUST be enforced at the view layer via `is_accessible`/`is_visible` and
`can_create`/`can_edit`/`can_delete` on every `ModelView`. Two roles are defined for
this iteration: `admin` (full CRUD everywhere) and `review_operator` (read-only on
organizations, read+edit on reviews, no access to user management). The admin panel is
additive: it MUST NOT modify existing API routes, scraper logic, or ORM models beyond
additive column additions. The application MUST start cleanly after each implementation
phase.

**Rationale**: The panel exposes all collected data and scrape controls; authentication
and RBAC protect it from unauthorized access in a shared internal environment.

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
Principle VII, and 2GIS review collection via its public reviews API (catalog + reviews
endpoints) per Principle VIII.

**Out of scope**: Posting replies, Google Maps and other map providers (except Yandex
and 2GIS), LLM/external-ML analysis, real-time notifications, TimescaleDB, forced
captcha bypass.

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

**Version**: 1.3.0 | **Ratified**: 2026-06-14 | **Last Amended**: 2026-07-03
