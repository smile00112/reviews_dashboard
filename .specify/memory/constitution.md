<!--
Sync Impact Report
Version change: (template) → 1.0.0
Modified principles: Initial ratification — all five principles defined
Added sections: MVP Scope Boundaries, Security & Credentials, Development Workflow
Removed sections: None (initial fill from template)
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check section aligns (no changes needed)
  ✅ .specify/templates/spec-template.md — scope alignment verified (no changes needed)
  ✅ .specify/templates/tasks-template.md — task categorization aligns (no changes needed)
Follow-up TODOs: None
-->

# ReviewsDashboard Constitution

## Core Principles

### I. MVP Scope Discipline

Every deliverable MUST stay within the documented MVP in/out-of-scope list. Features
explicitly excluded — application auth, review replies, Google Maps, 2GIS, LLM analysis,
WebSocket/email notifications, Celery pipelines, anti-captcha bypass — MUST NOT be
introduced without a constitution amendment and spec update.

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
Full TDD for every file is NOT required; tests MUST cover logic that would cause data
loss, duplicate reviews, or silent scrape failures.

**Rationale**: Duplicate reviews and lost scrape results are the highest-impact failure
modes for this product.

### IV. Scraper Reliability & Debuggability

Every scrape attempt MUST produce a scrape-run record with status, timestamps, counts,
and error details. Failed runs MUST save debug artifacts (screenshot and HTML snapshot
paths). Captcha, 2FA, or access challenges MUST surface as `needs_manual_action`, not
as generic failures or silent retries.

**Rationale**: Scraping is inherently fragile; operators need actionable failure signals.

### V. Simplicity (YAGNI)

Prefer the simplest architecture that satisfies the spec: FastAPI background tasks instead
of Celery, no application-level authentication, monorepo with `apps/api` and `apps/web`,
Docker Compose for local development. Additional services, queues, or abstractions MUST
be justified in the plan's Complexity Tracking table.

**Rationale**: MVP velocity and operability beat premature scaling infrastructure.

## MVP Scope Boundaries

**In scope**: Yandex Maps organization tracking, public and operator-auth scraping,
review display, manual scrape triggers (single and bulk), scrape history, deduplication,
debug artifacts for failures.

**Out of scope**: User login/roles, posting replies, other map providers, LLM features,
real-time notifications, TimescaleDB, forced captcha bypass.

**Scale assumption**: Internal tool for a small operator team tracking on the order of
tens of organizations, not thousands of concurrent users.

## Security & Credentials

Operator Yandex credentials MUST live in environment variables only. Playwright storage
state files MUST NOT be committed to version control. Passwords, cookies, and storage
state contents MUST NOT appear in logs or API responses. The `.local/` directory MUST
be gitignored.

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

**Version**: 1.0.0 | **Ratified**: 2026-06-14 | **Last Amended**: 2026-06-14
