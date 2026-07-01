<!--
Sync Impact Report
Version change: 1.1.0 → 1.2.0
Modified principles: None renamed
Added sections:
  - Principle VII. Admin Panel Security (new principle)
  - Admin Panel Security in Security & Credentials section
Modified sections:
  - MVP Scope Boundaries — removed "User login/roles" from out-of-scope;
    added "Internal admin panel (sqladmin) with RBAC" to in-scope.
Removed sections: None
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check section aligns (no changes needed)
  ✅ .specify/templates/spec-template.md — scope alignment verified (no changes needed)
  ✅ .specify/templates/tasks-template.md — task categorization aligns (no changes needed)
Follow-up TODOs: Feature 004 (admin panel) spec/plan to cite Principle VII.
-->

# ReviewsDashboard Constitution

## Core Principles

### I. MVP Scope Discipline

Every deliverable MUST stay within the documented MVP in/out-of-scope list. Features
explicitly excluded — review replies, Google Maps, 2GIS, LLM/external-ML analysis,
WebSocket/email notifications, Celery pipelines, anti-captcha bypass — MUST NOT be
introduced without a constitution amendment and spec update. Deterministic, rule-based
local analytics over already-collected reviews (see Principle VI) are in scope and do
NOT count as excluded "LLM analysis". The internal admin panel with RBAC (see
Principle VII) is in scope as of v1.2.0.

**Rationale**: The product is an internal read-only review collector; scope creep delays
the first working vertical slice.

### II. Read-Only Review Collection

The system MUST collect and display Yandex Maps reviews only. It MUST NOT publish,
edit, or delete replies on Yandex. Visible business responses MAY be stored when
present on the scraped page, but the product MUST NOT act as a reply management tool.

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

## MVP Scope Boundaries

**In scope**: Yandex Maps organization tracking, public and operator-auth scraping,
review display, manual scrape triggers (single and bulk), scrape history, deduplication,
debug artifacts for failures, structured (BeautifulSoup) review parsing with date
normalization, deterministic rule-based review analytics (sentiment, problem
categorization, rating↔sentiment mismatch) per Principle VI, and an internal admin
panel with authentication and role-based access control (admin + review_operator) per
Principle VII.

**Out of scope**: Posting replies, other map providers, LLM/external-ML analysis,
real-time notifications, TimescaleDB, forced captcha bypass.

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

**Version**: 1.2.0 | **Ratified**: 2026-06-14 | **Last Amended**: 2026-07-01
