# Tasks: Admin Panel with Authentication and RBAC

**Input**: Design documents from `specs/004-admin-panel/`

**Prerequisites**: [plan.md](plan.md) · [spec.md](spec.md) · [data-model.md](data-model.md) · [contracts/admin-auth.md](contracts/admin-auth.md) · [research.md](research.md) · [quickstart.md](quickstart.md)

**Tests**: Included in Phase 7 (required by spec §FR-002 critical-path testing rules).

**Organization**: Tasks grouped by implementation phase, each gating on `uvicorn` startup.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependency on incomplete tasks)
- **[US#]**: Maps to User Story in spec.md

---

## Phase 1: Setup — Dependencies and Config (Plan Phase 0)

**Purpose**: Install packages, extend config, wire SessionMiddleware.

**⚠️ Gate**: `uvicorn app.main:app` starts without errors after this phase.

- [X] T001 Add `sqladmin>=0.20` and `passlib[bcrypt]>=1.7.4` to `apps/api/pyproject.toml` dependencies
- [X] T002 [P] Add `admin_secret_key: str` and `session_max_age: int = 43200` fields to `apps/api/app/core/config.py` Settings class
- [X] T003 [P] Add `ADMIN_SECRET_KEY=change-me-in-production` and `SESSION_MAX_AGE=43200` to `apps/api/.env.example`
- [X] T004 Add `SessionMiddleware` import and `app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key, max_age=settings.session_max_age)` to `apps/api/app/main.py` (after CORSMiddleware)

**Checkpoint**: `cd apps/api && uvicorn app.main:app` starts without errors.

---

## Phase 2: Foundational — Models and Migration (Plan Phase 1)

**Purpose**: User model, enum extensions, additive columns, Alembic migration.

**⚠️ CRITICAL**: No admin functionality can work until migration applies cleanly.

- [X] T005 Add `UserRole(admin|review_operator)`, `ReviewStatus(new|in_progress|answered|escalated)`, `ReviewPlatform(yandex|google|gis2)` enums to `apps/api/app/models/enums.py`
- [X] T006 [P] Create `apps/api/app/core/security.py` with `hash_password(plain: str) -> str` and `verify_password(plain: str, hashed: str) -> bool` using `passlib.context.CryptContext(schemes=["bcrypt"])`
- [X] T007 Create `apps/api/app/models/user.py` — `User(Base)` model with columns: `id UUID PK`, `name TEXT`, `email TEXT UNIQUE NOT NULL`, `role UserRole NOT NULL`, `is_active BOOL DEFAULT TRUE`, `password_hash TEXT NOT NULL`, `default_location_id UUID FK organizations.id nullable`, `avatar_initials TEXT nullable`, `created_at TIMESTAMPTZ server_default now()`
- [X] T008 [P] Add nullable columns `city TEXT`, `region TEXT`, `is_franchise BOOL DEFAULT FALSE` to `Organization` model in `apps/api/app/models/organization.py`
- [X] T009 [P] Add nullable columns `status ReviewStatus`, `is_paid BOOL DEFAULT FALSE`, `platform ReviewPlatform`, `paid_cost INT nullable`, `paid_marked_by_user_id UUID FK users.id nullable`, `reply_text TEXT nullable`, `reply_at TIMESTAMPTZ nullable`, `replied_by_user_id UUID FK users.id nullable` to `Review` model in `apps/api/app/models/review.py`
- [X] T010 Add `from app.models.user import User` export to `apps/api/app/models/__init__.py`
- [X] T011 Add `from app.models.user import User  # noqa: F401` to the model imports block in `apps/api/alembic/env.py` (alongside existing Organization/Review imports) so Alembic autogenerate picks up the User table
- [X] T012 Generate and write Alembic migration `apps/api/alembic/versions/0004_admin_rbac.py` — `revises = "0003_public_http_mode"` — upgrade: create `user_role_enum`, `review_status_enum`, `review_platform_enum` types; create `users` table; add columns to `organizations` and `reviews`. Downgrade: reverse in opposite order.

**Checkpoint**: `cd apps/api && alembic upgrade head` applies without errors; `alembic downgrade -1` reverts cleanly; `alembic upgrade head` re-applies.

---

## Phase 3: User Story 1 — Secure Login (Plan Phases 2 + 3)

**Goal**: Mount sqladmin at `/admin`; implement login/logout/authenticate flow; unauthenticated redirect.

**Independent Test**: `GET /admin` → 302 to `/admin/login`. POST valid creds → `/admin/`. Wrong password → error. Inactive user → error. Logout clears session.

- [X] T013 Create `apps/api/app/admin/__init__.py` with `setup_admin(app, engine) -> Admin` function — initializes `Admin(app, engine, base_url="/admin", title="SERM Admin")` and returns the instance (no views registered yet)
- [X] T014 Wire `setup_admin` in `apps/api/app/main.py`: import `engine` from `app.core.database`, call `setup_admin(app, engine)` after middleware setup
- [X] T015 Create `apps/api/app/admin/auth.py` — `AdminAuth(AuthenticationBackend)` class with:
  - `login(request)`: read `username`/`password` from form; query User by email; `verify_password`; check `is_active`; write `user_id` and `role` to `request.session`; return True on success
  - `logout(request)`: clear `request.session`; return True
  - `authenticate(request)`: check `request.session.get("user_id")`; query User; check `is_active`; return User or redirect to login
- [X] T016 Update `apps/api/app/admin/__init__.py` — pass `authentication_backend=AdminAuth(secret_key=settings.admin_secret_key)` to the `Admin(...)` constructor

**Checkpoint** (US1): `GET /admin` → 302 `/admin/login`. Submit valid admin creds → 302 `/admin/`. Submit wrong password → 200 login with error. Inactive user → 200 login with error. Click logout → 302 `/admin/login`.

---

## Phase 4: User Stories 2 + 3 — RBAC (Plan Phase 4)

**Goal**: Role-gated views for UserAdmin, OrganizationAdmin, ReviewAdmin.

**Independent Test**: Under review_operator session: Users nav absent; org list read-only; review edit works; create/delete review denied.

- [X] T017 Create `apps/api/app/admin/base.py` — `RoleGatedModelView(ModelView)` base class with `_get_role(request) -> str | None` helper reading `request.session.get("role")`
- [X] T018 Create `apps/api/app/admin/views.py` with three view classes:
  - `UserAdmin(RoleGatedModelView)` for `User` — `is_accessible(request)`: role == "admin"; `is_visible(request)`: role == "admin"; full CRUD for admin
  - `OrganizationAdmin(RoleGatedModelView)` for `Organization` — accessible both roles; `can_create/can_edit/can_delete(request)` return `role == "admin"`
  - `ReviewAdmin(RoleGatedModelView)` for `Review` — accessible both roles; `can_create/can_delete(request)` return `role == "admin"`; `can_edit(request)` returns True for both. **Per-role form fields** (sqladmin technique): override `scaffold_form(request)` to return a filtered WTForm class when `_get_role(request) == "review_operator"` — the filtered form includes only `reply_text`, `status`, `is_paid` fields; the full form (for admin) includes all writable fields. Do NOT use a static `form_columns` class attribute for this — it is not per-request. Note: `paid_cost` and `paid_marked_by_user_id` must be absent from the operator form entirely.
- [X] T019 Register `UserAdmin`, `OrganizationAdmin`, `ReviewAdmin` via `admin.add_view()` calls in `apps/api/app/admin/__init__.py` `setup_admin()` function

**Checkpoint** (US2+US3): Log in as review_operator → no Users section; org list no action buttons; review edit form present with allowed fields only; POST to create/delete review → 403 or redirect.

---

## Phase 5: User Stories 4 + 5 — View Config (Plan Phase 5)

**Goal**: Column lists, search, filters, sort on OrganizationAdmin and ReviewAdmin.

**Independent Test**: Search by name → filtered results; franchise filter works; review status filter works; default sort newest first.

- [X] T020 [P] Configure `OrganizationAdmin` in `apps/api/app/admin/views.py`: `column_list = ["name","city","region","is_franchise","created_at"]`; `column_searchable_list = ["name","city"]`; `column_sortable_list = ["name","city","created_at"]`; `column_filters = ["city","region","is_franchise"]`; `column_labels = {"name":"Название","city":"Город","region":"Регион","is_franchise":"Франшиза","created_at":"Создана"}` ; add `__str__` returning `self.name or str(self.id)` to Organization model
- [X] T021 [P] Configure `ReviewAdmin` in `apps/api/app/admin/views.py`: `column_list = ["created_at","platform","organization_id","author_name","rating","status","is_paid"]`; `column_default_sort = ("created_at", True)`; `column_searchable_list = ["author_name","review_text"]`; `column_filters = ["platform","status","rating","is_paid"]`; `column_labels = {"author_name":"Автор","rating":"Оценка","status":"Статус","is_paid":"Покупной","created_at":"Дата"}` ; add `__str__` returning `f"{self.author_name} ({self.rating}★)"` to Review model

**Checkpoint** (US4+US5): Both list views load; search and filters return correct subsets; review list defaults to newest-first.

---

## Phase 6: User Story 6 — Seed Script (Plan Phase 6)

**Goal**: Idempotent CLI script to create initial admin and operator users.

**Independent Test**: Run twice → exactly 2 rows; passwords are hashes; re-run silent success.

- [X] T022 Create `apps/api/app/scripts/__init__.py` (empty, makes it a package)
- [X] T023 Create `apps/api/app/scripts/seed_users.py` — reads env vars `ADMIN_EMAIL` (default `admin@example.com`), `ADMIN_PASSWORD`, `OPERATOR_EMAIL` (default `operator@example.com`), `OPERATOR_PASSWORD`; for each user: query by email, skip if exists, else insert with `hash_password()`; uses `SessionLocal` directly; prints per-user status message; exits 0 always

**Checkpoint** (US6): `cd apps/api && ADMIN_PASSWORD=x OPERATOR_PASSWORD=y python -m app.scripts.seed_users` creates 2 users; re-run skips both; DB has hashed passwords.

---

## Phase 7: Polish and Acceptance — Tests (Plan Phase 7)

**Purpose**: Automated tests covering auth and RBAC; full acceptance checklist green.

- [X] T024 Create `apps/api/tests/test_admin_auth.py` with fixtures for in-memory SQLite + TestClient (extend conftest.py pattern); test cases:
  - `test_unauthenticated_redirect`: GET /admin → 302 location=/admin/login
  - `test_login_success`: POST /admin/login with correct creds → 302 /admin/
  - `test_login_wrong_password`: POST /admin/login wrong password → 200 (stays on login)
  - `test_login_inactive_user`: POST /admin/login for is_active=False user → 200 (denied)
  - `test_logout_clears_session`: login then GET /admin/logout → 302 /admin/login; subsequent GET /admin → 302 /admin/login
- [X] T025 Create `apps/api/tests/test_admin_rbac.py` with test cases:
  - `test_operator_no_users_access`: review_operator session GET /admin/user/list → 403 or 302 (denied)
  - `test_operator_org_read_only`: review_operator session GET /admin/organization/list → 200; no create/edit/delete in response
  - `test_operator_can_edit_review`: review_operator session POST review edit with reply_text → 200/302 success
  - `test_operator_cannot_edit_paid_cost`: review_operator session POST review edit with paid_cost value → field ignored (not in form)
  - `test_operator_cannot_create_review`: review_operator session POST /admin/review/create → 403 or redirect
  - `test_admin_full_crud`: admin session accesses Users, Orgs, Reviews list → all 200
  - `test_seed_idempotent`: call seed logic twice with same emails → exactly 2 User rows; `password_hash != plain password`
- [X] T026 Run `pytest apps/api/tests/test_admin_auth.py apps/api/tests/test_admin_rbac.py -v` and fix until all green
- [X] T027 Run full `pytest -v` to confirm no regressions in existing tests
- [X] T028 Walk through acceptance checklist in `specs/004-admin-panel/quickstart.md` and mark all items complete

**Checkpoint** (Final): All tests green; acceptance checklist complete; `uvicorn` starts; `/api/health` still returns `{"status":"ok"}`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (needs `admin_secret_key` in config)
- **Phase 3 (US1 Login)**: Depends on Phase 2 (needs User model + migration)
- **Phase 4 (US2+3 RBAC)**: Depends on Phase 3 (needs `Admin` instance + `AdminAuth`)
- **Phase 5 (US4+5 Views)**: Depends on Phase 4 (extends existing view classes)
- **Phase 6 (US6 Seed)**: Depends on Phase 2 (needs User model + SessionLocal)
- **Phase 7 (Tests)**: Depends on Phases 3–6 (tests all of the above)

### Within Each Phase

- Tasks marked `[P]` in same phase can run in parallel (different files)
- T008, T009 parallel with T007 (different model files)
- T020, T021 parallel with each other (different view configs)

---

## Parallel Opportunities

```bash
# Phase 2 — run T005, T006, T007, T008, T009 together:
T005: enums.py
T006: security.py     [P]
T007: user.py
T008: organization.py [P]
T009: review.py       [P]
# T010, T011, T012 sequentially after

# Phase 5 — run T020, T021 together:
T020: OrganizationAdmin column config [P]
T021: ReviewAdmin column config       [P]
```

---

## Implementation Strategy

### MVP (User Story 1 — Working Login)

1. Phase 1 → Phase 2 → Phase 3
2. Validate: login/logout works, unauthenticated redirect works
3. That's a deployable internal admin base

### Incremental Delivery

1. Phase 1+2 → Foundation
2. Phase 3 → Login MVP
3. Phase 4 → RBAC enforced
4. Phase 5 → Search/filter UX
5. Phase 6 → Seed convenience
6. Phase 7 → Green tests = shippable

---

## Notes

- `[P]` = different files, no cross-task deps, safe to parallelize
- `[US#]` label maps to user story in `spec.md`
- Run `uvicorn app.main:app` as gate after each phase
- Run `alembic upgrade head` gate after Phase 2
- Never hardcode passwords or `ADMIN_SECRET_KEY`
- Session cookie must be `HttpOnly` (Starlette's default)
