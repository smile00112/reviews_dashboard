---
description: "Task list for feature 016 — Roles & Permissions System"
---

# Tasks: Roles & Permissions System

**Input**: Design documents from `/specs/016-roles-permissions/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (roles-api, auth-me)

**Tests**: REQUIRED — RBAC allow/deny, role-CRUD guards, and migration mapping are
critical-path per Constitution Principle III. Test tasks are included and MUST be written
before (or alongside) the implementation they cover, and MUST fail first.

**Organization**: Grouped by user story. Backbone shared by all stories lives in Foundational.

## Path Conventions

Monorepo web app: backend `apps/api/app/…`, tests `apps/api/tests/…`; frontend
`apps/web/…`. Migration under `apps/api/alembic/versions/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new tooling needed — feature is additive to the existing stack. Confirm baseline.

- [ ] T001 Confirm baseline green before changes: run `pytest -v` in `apps/api` and `npm run lint` in `apps/web`; note the current migration head is `0023` (next is `0024`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Roles data model, permission catalog, resolution service, enforcement dependency,
and `/api/auth/me` payload — everything all four stories build on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 [P] Create the permission catalog in `apps/api/app/core/permissions.py`: `PAGE_PERMISSIONS` (11 keys), `ACTION_PERMISSIONS` (10 keys), `ALL_PERMISSIONS`, RU labels + category per key, and helper `is_valid_permission(key)`. NO reply/posting permission (FR-010).
- [ ] T003 [P] Create ORM models in `apps/api/app/models/role.py`: `Role` (id, name unique, slug unique, is_system, description, created_at) and `RolePermission` (role_id FK, permission; `UNIQUE(role_id, permission)`); `Role.permissions` relationship with `cascade="all, delete-orphan"` (SQLite-safe per research D5).
- [ ] T004 Modify `apps/api/app/models/user.py`: add `role_id` FK → `roles.id` (`ondelete="RESTRICT"`) + `role` relationship to `Role`; make legacy `role` enum column nullable (retained for rollback).
- [ ] T005 Author migration `apps/api/alembic/versions/0024_roles_permissions.py` (down_revision `0023`): create `roles` + `role_permissions`; seed admin/call_center/manager with default grants (data-model.md); add `users.role_id` (nullable), backfill from `users.role` (`admin→admin`, `review_operator→call_center`), then set `role_id` NOT NULL; keep `users.role` nullable. Downgrade reverses (restore `users.role` from `role.slug`, drop tables/column).
- [ ] T006 [P] Implement `apps/api/app/services/permission_service.py`: `PermissionService(db)` with `effective_permissions(user) -> set[str]` (admin `is_system` → `ALL_PERMISSIONS`, else grant rows) and `has_permission(user, perm)`.
- [ ] T007 Add `require_permission(perm)` dependency factory in `apps/api/app/api/deps.py` (builds on `get_current_user`, 403 on deny via `PermissionService`); keep `require_admin` as a thin alias that maps to an admin-equivalent check so legacy imports still resolve. Drop reliance on `request.session["role"]` (resolve via `role_id`).
- [ ] T008 [P] Add role schemas in `apps/api/app/schemas/role.py`: `RoleResponse` (id, slug, name, is_system, description, permissions[], user_count), `RoleCreate`, `RoleUpdate`, `GrantUpdate`, `PermissionCatalog`.
- [ ] T009 Update `apps/api/app/schemas/auth.py` `UserResponse`: replace bare `role` enum with a role object (`id/slug/name/is_system`) + `permissions: list[str]`; update `apps/api/app/api/auth.py` `/login`, `/me` to populate them via `PermissionService`.
- [ ] T010 [P] Frontend plumbing: extend `apps/web/lib/types.ts` (`Role`, `PermissionKey`, `CurrentUser.permissions[]`, `role` object) and `apps/web/components/shell/user-context.tsx` (`useCan(perm)`, `useCanPage(name)`); update `ROLE_LABEL`/user display in `sidebar.tsx` to read `role.name`.

**Checkpoint**: `alembic upgrade head` applies 0024; `GET /api/auth/me` returns role + permissions.

---

## Phase 3: User Story 4 - Existing users keep working after upgrade (Priority: P1) 🎯 MVP-critical

**Goal**: Deployment maps every existing account to a role with equivalent access; none role-less.

**Independent Test**: Seed pre-existing admin + review_operator users, run migration, assert mapping.

- [ ] T011 [US4] Migration mapping test in `apps/api/tests/test_role_migration.py`: seed a user per legacy role, run upgrade, assert `admin→admin` role, `review_operator→call_center`, `role_id` NOT NULL for all, and seeded roles + default grants exist. (Write to fail first.)
- [ ] T012 [US4] Update `apps/api/app/scripts/seed_users.py` to assign `role_id` (look up role by slug) instead of the enum; keep it idempotent.
- [ ] T013 [US4] Update `apps/api/tests/conftest.py` and any fixtures that construct `User(role=...)` to use `role_id`/seeded roles so the suite boots on the new model.

**Checkpoint**: Migration + suite bootstrap green; existing accounts preserved.

---

## Phase 4: User Story 1 - Grant a role access to pages (Priority: P1)

**Goal**: Admin grants page access per role; users see/enter only granted pages; backend + nav honor it.

**Independent Test**: Grant Call Center a page subset; that role's user sees only those nav items and is refused other pages.

- [ ] T014 [P] [US1] Test in `apps/api/tests/test_auth_me_permissions.py`: `/api/auth/me` returns the exact effective `permissions[]` per seeded role; admin returns full catalog. (Fail first.)
- [ ] T015 [US1] Sidebar page gating in `apps/web/components/shell/sidebar.tsx`: filter `NAV` items by `useCanPage(...)`; hide empty groups.
- [ ] T016 [US1] Server-side page entry guard for gated pages (`apps/web/app/(dashboard)/**/page.tsx` as needed): read `/api/auth/me`, redirect/404 when the page's `page:*` permission is absent. Start with the sensitive pages (settings, jobs, http_scraper, scrape_runs); apply the shared helper to the rest.
- [ ] T017 [US1] E2E in `apps/web/tests/roles.spec.ts` (part 1): admin grants a role a page subset, sign in as that role, assert nav shows only granted pages and a direct URL to a non-granted page is refused. (Depends on US3 roles UI for the grant step — until then, seed grants via API/DB in the test setup.)

**Checkpoint**: Page access is gated by nav + entry guard, driven by effective permissions.

---

## Phase 5: User Story 2 - Restrict actions within a page (Priority: P1)

**Goal**: Every mutating endpoint requires its specific action permission (403 on deny); UI hides the controls.

**Independent Test**: A role with `page:reviews` but not `action:review.edit_status` reads reviews but cannot change status (control hidden; PATCH → 403).

- [ ] T018 [P] [US2] RBAC enforcement tests in `apps/api/tests/test_rbac_permissions.py`: for each action gate (org.manage, company.manage, scrape.run, job.manage, review.edit_status, attention.manage, settings.edit, scraper_session.manage), assert allow (granted/admin), deny (403 without grant), and 401 unauthenticated. (Fail first.)
- [ ] T019 [US2] Re-point endpoint guards to `require_permission(...)` per the data-model.md route map: `organizations.py`, `companies.py`, `scrape_runs.py`, `scraper_sessions.py`, `jobs.py`, `reviews.py` (PATCH), `attention_rules.py`, `settings.py` — replacing the current `require_admin`.
- [ ] T020 [US2] Update `apps/api/tests/test_scrape_endpoints_require_admin.py` and `apps/api/tests/test_rbac.py` to the permission model (rename/retarget assertions; keep coverage of the admin-allowed path).
- [ ] T021 [P] [US2] Frontend action gating: wrap mutating controls in `useCan(...)` — review status/escalate controls (`apps/web/app/(dashboard)/reviews/…` + components), scrape triggers, job run/update, attention-rule and settings write buttons.
- [ ] T022 [US2] Extend `apps/web/tests/roles.spec.ts` (part 2): role with page but not action — control hidden and a direct mutating request is refused (403); after admin grants the action, control appears and succeeds.

**Checkpoint**: Actions are enforced server-side and mirrored in the UI.

---

## Phase 6: User Story 3 - Manage custom roles (Priority: P2)

**Goal**: Admin creates/renames/deletes roles and edits the grant matrix from a settings page; guards hold.

**Independent Test**: Create a role, assign grants, rename, fail to delete while in use (409), reassign, delete.

- [ ] T023 [P] [US3] Roles API tests in `apps/api/tests/test_roles_api.py`: catalog shape; list with user_count + admin `["*"]`; create (dup name→409, blank→422, unknown perm→422); PATCH rename (admin→403); PUT grants (admin→403, full replace); DELETE (admin→403, in-use→409, success→204). (Fail first.)
- [ ] T024 [US3] Implement `apps/api/app/services/role_service.py`: create/rename/update-grants/delete with guards (is_system immutable, in-use 409, name unique/non-empty, slug derivation, catalog validation).
- [ ] T025 [US3] Implement `apps/api/app/api/roles.py` router (prefix `/api/roles`, guarded by `require_permission("action:roles.manage")`): `GET /catalog`, `GET /`, `POST /`, `PATCH /{id}`, `PUT /{id}/permissions`, `DELETE /{id}`; register the router in `apps/api/app/main.py`.
- [ ] T026 [P] [US3] Frontend API client in `apps/web/lib/api.ts`: `getPermissionCatalog`, `getRoles`, `createRole`, `updateRole`, `updateRoleGrants`, `deleteRole`.
- [ ] T027 [US3] Build the Roles & Access page: `apps/web/app/(dashboard)/settings/roles/page.tsx` (guarded by `page:roles`) + components under `apps/web/components/settings/roles/` (`role-list.tsx`, `role-matrix.tsx` grouped Pages/Actions checkboxes, `role-form.tsx` create/rename). Admin row rendered fully-checked + disabled.
- [ ] T028 [US3] Add the "Роли и доступ" nav entry (group «Система») in `apps/web/components/shell/sidebar.tsx`, gated by `page:roles`.

**Checkpoint**: Full role lifecycle works through the UI; guards enforced.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T029 [P] Update the sqladmin gate to slug-based admin: `apps/api/app/admin/auth.py` and `apps/api/app/admin/views.py` use `role.slug == "admin"` (via `role_id`); update `apps/api/tests/test_admin_rbac.py` / `test_admin_auth.py` accordingly.
- [ ] T030 [P] Update `CLAUDE.md` Architecture section with a short "Roles & permissions (feature 016)" subsection (catalog, require_permission, admin immutable, migration 0024, contracts).
- [ ] T031 Run the quickstart.md validation end-to-end: `pytest -v` (api) then `npm run lint && npm run test:e2e` (web); fix any gaps. Confirm the catalog exposes no reply permission and the sqladmin panel admits only admin-slug users.

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** blocks everything.
- **US4 (Phase 3)** depends only on Foundational; do first (it makes the suite boot on the new model).
- **US1 (Phase 4)** and **US2 (Phase 5)** depend on Foundational; independently testable. US1's E2E grant step is smoother after US3's UI but can seed grants via API/DB meanwhile.
- **US3 (Phase 6)** depends on Foundational; unlocks the matrix UI used by US1/US2 E2E.
- **Polish (Phase 7)** after the stories.

### Within a story

- Tests written first and failing, then implementation.
- Models → services → endpoints → UI.

### Parallel opportunities

- Foundational: T002, T003, T006, T008, T010 are `[P]` (distinct files); T004→depends on T003; T005→after models; T007→after T006; T009→after T006.
- Test-authoring tasks (T014, T018, T023) are `[P]` across stories.
- Frontend gating (T021) and backend guard swap (T019) touch different trees — parallelizable.

---

## Implementation Strategy

### MVP scope

Foundational + **US4** (continuity) + **US1** (page gating) + **US2** (action gating) = the
operator's core ask ("страница доступа к страницам" + "ограничивать действия"). **US3** (custom-role
management UI) is the next increment; until it lands, the three seeded roles + API cover daily use.

### Incremental delivery

1. Setup + Foundational → migration applies, `/me` exposes permissions.
2. US4 → suite boots on new model; existing users preserved. Deploy-safe.
3. US1 → pages gated. Demo.
4. US2 → actions gated. Demo.
5. US3 → full role management UI. Demo.
6. Polish → sqladmin slug gate, docs, quickstart.

---

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Commit after each task or logical group.
- Verify each test fails before implementing its target (Principle III / TDD).
- Do NOT introduce any provider-reply permission; do NOT change `build_review_hash` / dedup.
- Keep the single auth system; no JWT/second identity store.
