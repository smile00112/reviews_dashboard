# Research: Roles & Permissions System (feature 016)

All Technical Context unknowns were resolvable from the existing codebase and constitution
v1.5.0; no external research was required. This document records the design decisions.

## D1. Permission representation

- **Decision**: Opaque string keys in two namespaces — `page:<name>` and `action:<name>` —
  enumerated as constants in `apps/api/app/core/permissions.py`, which is the single source
  of truth. A grant is a `role_permissions(role_id, permission)` row; absence = deny.
- **Rationale**: Strings are trivial to store, transmit, and check; grouping by `page:` /
  `action:` prefix lets the matrix UI and `/catalog` endpoint categorize without a second
  table. Matches the existing enum-value-as-string convention (`ScrapeMode`, etc.).
- **Alternatives considered**: (a) a `permissions` table with FK grants — rejected as
  over-normalized for a fixed, code-defined catalog (YAGNI, Principle V); (b) a bitmask —
  rejected as opaque and migration-hostile when the catalog grows.

### Catalog (v1)

**Pages** (`page:`): `overview, ratings, companies, organizations, reviews, scrape_runs,
jobs, attention_rules, http_scraper, settings, roles` (11).

**Actions** (`action:`): `org.manage, company.manage, scrape.run, job.manage,
review.edit_status, attention.manage, settings.edit, scraper_session.manage, users.manage,
roles.manage` (10).

Explicitly **excluded**: any `reply.*` / posting-to-provider permission (Principle II).

## D2. The immutable `admin` role

- **Decision**: `admin` is the sole `is_system=true` role, slug `admin`. `PermissionService`
  returns the entire catalog for any user whose role is `is_system` admin, **without** storing
  grant rows for it. Role CRUD refuses to delete/rename it or edit its grants.
- **Rationale**: Storing "all permissions" as rows would drift as the catalog grows and could
  be partially revoked by a bug; a code-level shortcut guarantees the "always full access,
  never downgradable" invariant (FR-003) structurally.
- **Alternatives considered**: seeding admin with every grant row — rejected (drift + the
  invariant becomes data-dependent rather than guaranteed).

## D3. Enforcement point & staleness

- **Decision**: Resolve effective permissions **per request** from the DB via a
  `require_permission(perm)` dependency built on `get_current_user`. One indexed query on
  `role_permissions` by `role_id`. Drop the login-time `request.session["role"]` string; look
  up `role_id` each time.
- **Rationale**: Spec edge case — an admin editing a role's grants must take effect on the
  user's next request; a session-cached permission set would honor a revoked grant. The tool's
  scale (a handful of users) makes per-request lookup free.
- **Alternatives considered**: caching permissions in the signed session — rejected (stale
  grants); a short TTL cache — rejected as premature optimization (Principle V).

## D4. `require_admin` continuity

- **Decision**: Keep `require_admin` as a thin compatibility alias, but re-point every current
  call site to its specific `require_permission(...)` (mapping in data-model.md). So action
  gating is real from day one rather than "admin-only for everything".
- **Rationale**: FR-009/FR-015 require real action permissions now (the operator asked to gate
  actions, not just pages). A blanket admin alias would defer the actual feature.
- **Alternatives considered**: leaving `require_admin` everywhere and only gating pages —
  rejected (fails FR-009 and User Story 2).

## D5. SQLite test compatibility

- **Decision**: `Role.permissions` → `RolePermission` relationship uses
  `cascade="all, delete-orphan"`; deleting a `Role` ORM object removes its grant rows in
  Python, so history/grants die with the role even with the FK pragma off in tests.
- **Rationale**: Directly reuses the feature-015 `AttentionEvent` pattern documented in
  CLAUDE.md; keeps `test_*` on SQLite green.
- **Alternatives considered**: relying on DB `ON DELETE CASCADE` only — rejected (SQLite tests
  disable FK enforcement).

## D6. Migration strategy & rollback

- **Decision**: Migration 0024 (a) creates `roles` + `role_permissions`, (b) seeds admin /
  call_center / manager with default grants, (c) adds `users.role_id` (FK, nullable during
  migration), (d) backfills `role_id` from the old `users.role` value (`admin→admin`,
  `review_operator→call_center`), (e) makes `role_id` NOT NULL after backfill, (f) leaves
  `users.role` nullable (retained for rollback). Downgrade drops the FK/tables and restores
  `users.role` from `role.slug`.
- **Rationale**: Zero-downtime, no account left role-less (FR-005/FR-020), reversible.
- **Alternatives considered**: dropping `users.role` immediately — rejected (no safe
  rollback path in the same release; deferred to a later cleanup migration per plan D6).

### Default grants for seeded roles

- **admin**: full access (via D2 shortcut; no rows).
- **call_center**: pages `overview, ratings, reviews`; action `review.edit_status`.
- **manager**: pages `overview, ratings, companies, organizations, reviews, scrape_runs,
  jobs, attention_rules`; no `users.manage` / `roles.manage` / `settings.edit`.

These defaults map the *previous* effective access as closely as possible (the old
`review_operator` was read-only in the JSON API + edit reviews) and give `manager` a broader
read/analytics footprint — refined if the operator requests different defaults.

## D7. Frontend mirroring

- **Decision**: `/api/auth/me` returns `role: {slug, name, is_system}` and
  `permissions: string[]`. `user-context.tsx` exposes `useCan(perm)` / `useCanPage(name)`;
  `sidebar.tsx` filters `NAV` by `page:*`; server components for gated pages check the
  permission and 404/redirect when absent (defense stays server-side too via the API).
- **Rationale**: FR-017/FR-019; keeps `middleware.ts` as the existing cheap cookie check.
- **Alternatives considered**: encoding permissions in the cookie — rejected (staleness, and
  it grows the signed cookie).
