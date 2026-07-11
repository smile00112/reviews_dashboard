# Tasks: Admin Control Panel (auth + Company/Branch management)

**Feature**: 008-admin-dashboard | **Branch**: `feature/008-admin-dashboard`
**Inputs**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

Paths are repo-relative. `[P]` = parallelizable (different files, no incomplete dependency).

## Phase 1: Setup

- [ ] T001 Confirm branch `feature/008-admin-dashboard` and `.env` has `DATABASE_URL` + `ADMIN_SECRET_KEY`; verify `alembic current` head is `0007_response_first_seen` in apps/api
- [ ] T002 [P] Add dark palette from docs/plans/dashboard_prototype.html `:root` vars to apps/web/tailwind.config.js (`theme.extend.colors`: bg/surface/surface-2/surface-3/border/text/text-dim/text-faint/accent/good/warn/bad/info)
- [ ] T003 [P] Add prototype CSS variables + font wiring to apps/web/app/globals.css and load Fraunces/Manrope/JetBrains Mono via next/font/google in apps/web/app/layout.tsx

## Phase 2: Foundational (blocks all user stories)

**Data backbone**

- [ ] T004 Create migration apps/api/alembic/versions/0008_companies.py (`down_revision="0007_response_first_seen"`): create `companies` table (id UUID PK, name Text NOT NULL, is_active Bool server_default true, created_at/updated_at) + add `organizations.company_id` UUID nullable FK→companies.id ON DELETE SET NULL + index `ix_organizations_company_id`; portable UUID per 0004_admin_rbac.py; downgrade reverses. Add comment noting 007-merge reconciliation.
- [ ] T005 [P] Create Company ORM in apps/api/app/models/company.py (`branches` relationship back_populates `company`, no cascade)
- [ ] T006 Add `company_id` column + `company` relationship to apps/api/app/models/organization.py (do NOT touch content_hash/dedup/review FKs)
- [ ] T007 [P] Create apps/api/app/schemas/company.py (`CompanyCreate`, `CompanyUpdate`, `CompanyResponse` with `branch_count`)
- [ ] T008 Extend apps/api/app/schemas/organization.py: `OrganizationCreate` + optional name/city/region/address/company_id; `OrganizationUpdate` + optional city/region/address/company_id; `OrganizationResponse` + city/region/company_id
- [ ] T009 Run `alembic upgrade head` in apps/api and confirm `companies` table + `organizations.company_id` exist (SC gate: app starts clean)

**Auth surface (reuse feature-004)**

- [ ] T010 [P] Create apps/api/app/api/deps.py: `get_current_user(request)` from `request.session["user_id"]` (401 if missing) + `require_admin` (403 if role != admin)
- [ ] T011 Create apps/api/app/api/auth.py router: POST /api/auth/login (verify via core/security.verify_password, set session user_id/role, 401 on bad creds, 403 inactive), POST /api/auth/logout (204), GET /api/auth/me (200/401) per contracts/auth-api.md
- [ ] T012 Register auth router in apps/api/app/main.py (SessionMiddleware already mounted)

**Frontend auth transport**

- [ ] T013 [P] Add `rewrites()` mapping `/api/:path*` → API base in apps/web/next.config.ts
- [ ] T014 Switch apps/web/lib/api.ts `request<T>` to relative `/api` paths + `credentials:"include"`; add `login`, `logout`, `getMe`
- [ ] T015 [P] Add `Company` type + extend `Organization` (city/region/company_id) in apps/web/lib/types.ts

**Checkpoint**: migrations apply, app starts, `/api/auth/*` reachable, web talks to API same-origin.

## Phase 3: User Story 1 — Operator signs in (P1) 🎯 MVP

**Goal**: Auth gate — unauthenticated redirects to /login; valid creds reach the shell; sign-out works.
**Independent test**: quickstart §3.

- [ ] T016 [P] [US1] Create dark login form at apps/web/app/login/page.tsx → `login()` then redirect to /companies; show error on 401
- [ ] T017 [P] [US1] Create apps/web/components/shell/sidebar.tsx + apps/web/components/shell/topbar.tsx (user card + sign-out) from prototype markup
- [ ] T018 [US1] Create apps/web/app/(dashboard)/layout.tsx — render shell; server-side guard calling GET /api/auth/me, redirect to /login on 401
- [ ] T019 [US1] Create apps/web/middleware.ts — redirect unauthenticated dashboard routes to /login (session-cookie presence check)
- [ ] T020 [P] [US1] Add apps/api/tests/test_auth.py: login success→200+session, wrong password/unknown email→401, /me without session→401, logout→204 then /me→401

**Checkpoint**: US1 independently testable — sign-in flow complete.

## Phase 4: User Story 2 — Admin creates an Organization/company (P1)

**Goal**: Company CRUD; created company shows with 0 branches.
**Independent test**: quickstart §4.

- [ ] T021 [US2] Create apps/api/app/services/company_service.py: `list_all`, `get`, `create`, `update`, `delete` (delete relies on FK SET NULL), `branch_count`
- [ ] T022 [US2] Create apps/api/app/api/companies.py: GET/POST(list/create), GET/PATCH/DELETE `/{id}` per contracts/companies-api.md; writes guarded by `require_admin`, reads by `get_current_user`; register router in apps/api/app/main.py
- [ ] T023 [P] [US2] Add apps/api/tests/test_company_service.py: create→list, update, delete-with-branch keeps branch (company_id NULL), branch_count reflects assigned branches
- [ ] T024 [P] [US2] Add company API methods to apps/web/lib/api.ts (listCompanies/createCompany/getCompany/updateCompany/deleteCompany/getCompanyBranches)
- [ ] T025 [P] [US2] Create apps/web/components/company-form.tsx (create/edit; mirrors organization-form.tsx pattern)
- [ ] T026 [US2] Create apps/web/app/(dashboard)/companies/page.tsx — list companies + create/edit/delete (admin only controls)

**Checkpoint**: US2 independently testable — company management works.

## Phase 5: User Story 3 — Admin adds Branches grouped by city (P1)

**Goal**: Add/edit/delete branches under a company; grouped by city; collection unchanged.
**Independent test**: quickstart §5–6.

- [ ] T027 [US3] Extend apps/api/app/services/organization_service.py `create`/`update` to persist company_id/city/region/address; validate company_id exists; add optional company filter to list
- [ ] T028 [US3] Add `list_branches_grouped_by_city(company_id)` to apps/api/app/services/company_service.py (ordered by city then name; NULL/empty city → "Без города" last)
- [ ] T029 [US3] Add GET `/api/companies/{id}/branches` (grouped) to apps/api/app/api/companies.py; add `?company_id=` filter + new-field acceptance + `require_admin` guards on org POST/PATCH/DELETE in apps/api/app/api/organizations.py per contracts/organizations-ext.md
- [ ] T030 [P] [US3] Add apps/api/tests/test_organization_company.py: create org with company_id+city persists + appears in grouped branches; update city moves group; update company_id reassigns
- [ ] T031 [P] [US3] Create apps/web/components/branch-form.tsx (name, city, yandex_url, address, mode) as the add/edit-branch modal (prototype modalAddLocation)
- [ ] T032 [US3] Create apps/web/app/(dashboard)/companies/[id]/page.tsx — company detail, branches grouped by city, add/edit/delete branch via modal

**Checkpoint**: US3 independently testable — core Organization→city→branch flow works end-to-end.

## Phase 6: User Story 4 — Read-only operator prevented from writing (P2)

**Goal**: review_operator can read but not write; controls hidden and writes refused.
**Independent test**: quickstart §7.

- [ ] T033 [US4] Verify/complete `require_admin` on all company + org write routes (companies POST/PATCH/DELETE, organizations POST/PATCH/DELETE)
- [ ] T034 [P] [US4] Add apps/api/tests/test_rbac.py: review_operator GET→200, POST/PATCH/DELETE company & org→403; unauthenticated→401
- [ ] T035 [US4] Gate create/edit/delete controls in apps/web company + branch pages by current user role from getMe (hide for review_operator)

**Checkpoint**: US4 independently testable — RBAC enforced UI + API.

## Phase 7: User Story 5 — Existing views inside the shell (P3)

**Goal**: reviews/scrape-history/session views reachable within the panel shell.
**Independent test**: quickstart — navigate to reviews/history within shell.

- [ ] T036 [P] [US5] Move/rewire apps/web/app/organizations, /reviews, /scrape-runs, /http-scraper under the (dashboard) shell nav (sidebar links); light restyle only, no behavior change

## Phase 8: Polish & Verification

- [ ] T037 Run `pytest -v` in apps/api — all green INCLUDING unchanged test_review_deduplication.py + normalization/hash tests (dedup regression gate, SC-005)
- [ ] T038 [P] Run `npm run lint` in apps/web; fix lint issues
- [ ] T039 [P] Add Playwright smoke to apps/web/tests: login → create company → add branch (SHOULD, constitution III)
- [ ] T040 Execute quickstart.md end-to-end manually: auth gate, create company, add branches by city, trigger scrape on a branch (dedup intact), read-only role refused
- [ ] T041 Update .env.example if any new setting is introduced; confirm no plaintext secrets in code/logs

## Dependencies

- Phase 1 → Phase 2 → (Phase 3 US1 required before US2/US3 UI is usable, but backend of US2/US3 is independent of US1).
- Backend order: T004→T006/T009 (migration+models) before T021/T027 (services). T010–T012 (auth) before T022/T029 guards and before T033/T034.
- Frontend: T013–T015 before any web page; T016–T019 (US1) before dashboard pages render guarded; T024 before T026/T032.
- US4 (T033) depends on write routes existing (T022, T029). US5 (T036) depends on shell (T017–T018).

## Parallel opportunities

- Setup: T002, T003 together.
- Foundational: T005+T007 (models/schemas), T010+T013+T015 (deps/rewrite/types) in parallel.
- US1: T016, T017, T020 in parallel; T018/T019 after shell exists.
- US2: T023, T024, T025 in parallel after T021/T022.
- US3: T030, T031 in parallel after T027–T029.
- Polish: T038, T039 in parallel.

## MVP scope

**US1 + US2 + US3** (all P1) = the delivered MVP: sign in, create an Organization, add its Branches grouped by city with collection unchanged. US4 (RBAC hardening) and US5 (fold existing views) follow.
