# Implementation Plan: Roles & Permissions System

**Branch**: `016-roles-permissions` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-roles-permissions/spec.md`

## Summary

Replace the fixed two-value `UserRole` enum (`admin`/`review_operator`) with an
admin-managed configurable RBAC model: a `roles` table, a `role_permissions` grant matrix,
and a `users.role_id` FK. A static permission **catalog** (page + action permissions) lives
in code; grants live in the DB. The backend is the enforcement source of truth via a new
`require_permission("<perm>")` FastAPI dependency (403 deny / 401 unauthenticated) that
replaces the per-route `require_admin` guards; `admin` is an immutable `is_system` role that
short-circuits to full access. `/api/auth/me` gains the caller's `role` object and effective
`permissions[]`; the web app mirrors them (nav filtering, button gating) for UX only. A new
`/settings/roles` page renders an editable role×permission matrix and role CRUD. Migration
**0024** seeds three roles (admin, call_center, manager) with default grants and maps
existing users (`admin→admin`, `review_operator→call_center`), keeping the old `users.role`
column nullable for rollback. The sqladmin panel keeps gating on `role.slug == "admin"`.

## Technical Context

**Language/Version**: Python 3.11 (apps/api), TypeScript / Next.js App Router (apps/web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, Starlette
SessionMiddleware, sqladmin, passlib[bcrypt]; Next.js 14 (React server + client components)

**Storage**: PostgreSQL 16 (prod), SQLite (test backends). New tables `roles`,
`role_permissions`; new column `users.role_id`; `users.role` retained nullable.

**Testing**: pytest (apps/api), Playwright E2E (apps/web)

**Target Platform**: Linux server (Docker Compose), internal tool

**Project Type**: Web application (apps/api backend + apps/web frontend, monorepo)

**Performance Goals**: Negligible — permission resolution is one small indexed query per
request (or cached on the session); no impact on the feature-012 dashboard query-count
contract (RBAC touches auth deps, not the dashboard aggregation).

**Constraints**: Additive ORM changes only; dedup contract frozen; single auth system; no
posting-replies permission; SQLite test compatibility (FK pragma off in tests — mirror the
feature-015 pattern of ORM `cascade="all, delete-orphan"` for `role_permissions`).

**Scale/Scope**: Tens of organizations, a handful of operator accounts, ~3–6 roles,
~21 catalog permissions (11 pages + 10 actions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution **v1.5.0** (amended for this feature).

| Principle | Assessment |
|-----------|------------|
| I. MVP Scope Discipline | ✅ Configurable RBAC is explicitly in scope as of v1.5.0. |
| II. Read-Only Collection | ✅ No provider writes; posting replies is NOT a grantable permission (FR-010). |
| III. Critical-Path Testing | ✅ Plan mandates RBAC allow/deny/403 per gate, role-CRUD guards, migration-mapping tests. |
| IV. Scraper Debuggability | ✅ Untouched (scrape.run gate wraps existing endpoints; behavior unchanged). |
| V. Simplicity (YAGNI) | ✅ One catalog module + one service + one dependency + one migration; no new infra, no per-record scoping. |
| VI. Deterministic Local Analytics | ✅ Untouched. |
| VII. Admin Panel Security & Configurable RBAC | ✅ This feature IS Principle VII v1.5.0: backend-enforced, `admin` immutable, single auth, `/api/auth/me` exposes permissions. |
| VIII. Multi-Provider Collection | ✅ Untouched. |

**Gate result: PASS.** No violations; Complexity Tracking not required.

Dedup contract (`build_review_hash`, `uq_review_org_hash`) untouched. `users.role` column
retained (nullable) for rollback — an additive change, not a dedup/schema-breaking one.

## Project Structure

### Documentation (this feature)

```text
specs/016-roles-permissions/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (roles + auth/me API contracts)
│   ├── roles-api.md
│   └── auth-me.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/api/app/
├── models/
│   ├── enums.py             # UserRole kept (legacy col); add PermissionCategory if useful
│   ├── role.py              # NEW: Role, RolePermission ORM models
│   └── user.py              # + role_id FK (Mapped), relationship("Role"); role now nullable
├── core/
│   └── permissions.py       # NEW: static catalog (PAGE_*/ACTION_* constants) + default grants
├── services/
│   ├── permission_service.py  # NEW: effective permissions for a user (admin → all)
│   └── role_service.py        # NEW: role CRUD + grant editing + guards (is_system/in-use)
├── api/
│   ├── deps.py              # + require_permission(perm) factory; require_admin → alias
│   ├── auth.py              # /api/auth/me returns role + permissions[]
│   └── roles.py             # NEW: /api/roles CRUD + /api/roles/catalog + PUT grants
├── schemas/
│   ├── auth.py              # UserResponse: role obj + permissions[]
│   └── role.py              # NEW: RoleResponse, RoleCreate/Update, PermissionCatalog, GrantUpdate
├── admin/
│   ├── auth.py              # gate on role.slug == "admin" (role via role_id)
│   └── views.py             # is_accessible uses role.slug == "admin"
└── scripts/
    └── seed_users.py        # seed against roles table (role_id)

apps/api/alembic/versions/
└── 0024_roles_permissions.py  # NEW: tables + seed + user mapping + role_id FK

apps/api/tests/
├── test_roles_api.py            # NEW: CRUD + guards (is_system, in-use 409, dup/blank name)
├── test_rbac_permissions.py     # NEW: require_permission allow/deny/403/401 per gate
├── test_auth_me_permissions.py  # NEW: effective permission set per role; admin → all
├── test_role_migration.py       # NEW: old→new mapping (admin→admin, review_operator→call_center)
├── test_rbac.py                 # UPDATED to new model
├── test_scrape_endpoints_require_admin.py  # UPDATED (now permission-based)
└── test_admin_rbac.py / test_admin_auth.py # UPDATED (slug-based gate)

apps/web/
├── lib/
│   ├── types.ts             # Role, Permission, CurrentUser.permissions[]; PermissionKey union
│   └── api.ts               # getRoles, createRole, updateRole, deleteRole, getPermissionCatalog, updateRoleGrants
├── components/shell/
│   ├── user-context.tsx     # provide permissions; useCan(perm), useCanPage(page)
│   └── sidebar.tsx          # filter NAV by page permission; ROLE_LABEL from role.name
├── components/settings/
│   └── roles/               # NEW: role-matrix.tsx, role-list.tsx, role-form.tsx
├── app/(dashboard)/settings/roles/
│   └── page.tsx             # NEW: Roles & Access page (guarded by page:roles)
└── tests/roles.spec.ts      # NEW E2E: admin edits matrix → role user's nav/actions change
```

**Structure Decision**: Existing monorepo web-application layout (`apps/api` FastAPI +
`apps/web` Next.js). The feature is additive within the established backend layering
(api→services→models→schemas) and the App Router page/component split. New concerns get
their own focused modules: `core/permissions.py` (catalog is the single source of truth),
`services/permission_service.py` (effective-permission resolution), `services/role_service.py`
(role lifecycle), `api/roles.py` (CRUD). The `require_permission` dependency lives beside the
existing `require_admin` in `api/deps.py`.

## Key Design Decisions (resolved in research.md)

1. **Permission representation**: opaque string keys in a `page:*` / `action:*` namespace,
   enumerated in `core/permissions.py`. A grant = a `role_permissions` row. Absence = deny.
2. **`admin` shortcut**: `PermissionService` returns the full catalog for any user whose role
   is `is_system` + slug `admin`; no grant rows are stored for admin, so it can never be
   "partially" configured. `require_permission` and `/api/auth/me` both go through it.
3. **`require_admin` continuity**: kept as a thin alias mapping to the manage-style
   permissions so existing call sites keep compiling, but every route is re-pointed to its
   specific `require_permission(...)` (e.g. `scrape.run`, `job.manage`) so action gating is
   real from day one.
4. **Session vs. per-request resolution**: resolve permissions per request from the DB (one
   indexed query) — no stale grants after an admin edits the matrix (spec edge case). The
   login-time `request.session["role"]` string is dropped in favour of `role_id` lookups.
5. **SQLite tests**: `role_permissions` uses ORM `cascade="all, delete-orphan"` so deleting a
   role removes its grants even with FK pragma off (feature-015 pattern).
6. **Rollback**: keep `users.role` nullable and backfilled during migration; a later feature
   drops it once the new model is proven.

## Complexity Tracking

No constitution violations — table intentionally omitted.
