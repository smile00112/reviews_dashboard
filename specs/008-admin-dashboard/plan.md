# Implementation Plan: Admin Control Panel (auth + Company/Branch management)

**Branch**: `feature/008-admin-dashboard` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-admin-dashboard/spec.md`

## Summary

Add a custom, dark, branded Next.js control panel (styled after `docs/plans/dashboard_prototype.html`) that requires sign-in and lets an admin manage a new **Company** parent entity and its **Branches** (the existing `organizations` scrape points) grouped by city. Auth reuses the feature-004 stack unchanged (`users` table, `UserRole`, bcrypt, `SessionMiddleware` signed with `ADMIN_SECRET_KEY`) — the JSON API gains a small session-cookie auth surface (`/api/auth/*`) and a `get_current_user` dependency guarding the write routes. Data model is additive: one new `companies` table plus a nullable `organizations.company_id` FK; **reviews, `build_review_hash`, `uq_review_org_hash`, and the scraper flow are untouched** — `organizations` stays the scrape/dedup unit. Scope v1 = login + admin cabinet + Company/Branch CRUD; prototype analytics screens are deferred.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI backend), TypeScript 5.7 / React 19 (Next.js 15.1 App Router frontend)

**Primary Dependencies**: Backend — FastAPI, SQLAlchemy, Alembic, `starlette.middleware.sessions.SessionMiddleware` (already mounted), `passlib[bcrypt]` (already present), sqladmin (unchanged). Frontend — Next.js 15.1, React 19, Tailwind CSS 3.4, `next/font/google` (Fraunces / Manrope / JetBrains Mono). No new auth library, no JWT, no chart lib (analytics deferred).

**Storage**: PostgreSQL 16 (SQLite for backend tests via `JSON().with_variant(JSONB)` pattern already in repo). New `companies` table + additive `organizations.company_id` column.

**Testing**: pytest (`apps/api/tests`) for auth, RBAC, company CRUD, org-field persistence, plus unchanged dedup/normalization regression; Playwright (`apps/web`) smoke for login → create company → add branch (SHOULD).

**Target Platform**: Linux server (Docker Compose: web :3000, api :8000). Internal LAN tool.

**Project Type**: Web application (monorepo `apps/api` FastAPI + `apps/web` Next.js).

**Performance Goals**: Interactive admin CRUD for a small team; no throughput targets. Branch list groups tens of branches per company.

**Constraints**: Additive-only ORM changes; dedup contract frozen; single auth system (reuse 004); session cookie must reach the browser (solved via same-origin Next.js `/api` rewrite). Application MUST start cleanly after each phase.

**Scale/Scope**: Tens of organizations, a handful of operators. ~1 new table, ~3 new backend modules (auth, companies router, company service), ~6 new frontend routes/components.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution **v1.4.0**.

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ Pass | Custom control panel + Company entity added to scope in v1.4.0 amendment; no excluded features (no replies, no Google, no LLM). |
| II. Read-Only Review Collection | ✅ Pass | No collection/publish changes; branches reuse existing read-only scrape points. |
| III. Critical-Path Testing | ✅ Pass | Adds auth success/failure + RBAC tests, company CRUD & org-field contract tests; existing dedup/normalization tests kept green (regression gate). |
| IV. Scraper Reliability & Debuggability | ✅ Pass | Scraper untouched; scrape-run records unchanged. |
| V. Simplicity (YAGNI) | ✅ Pass | Reuse existing auth + existing org as branch; one additive table; no city catalog, no queue, no new auth lib. |
| VI. Deterministic Local Analytics | ✅ Pass | Analytics untouched and deferred. |
| VII. Admin Panel Security | ✅ Pass | Reuses `users`/roles/bcrypt/`ADMIN_SECRET_KEY` session; RBAC admin=full, review_operator=read-only; write routes guarded; dedup frozen; additive ORM. |
| VIII. Multi-Provider Collection | ✅ Pass | No provider/dedup path change; branches carry the existing `preferred_scrape_mode`. |

**Post-Design re-check**: No new violations after Phase 1 design — all changes remain additive; no Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/008-admin-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (auth, companies, organizations-ext)
│   ├── auth-api.md
│   ├── companies-api.md
│   └── organizations-ext.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/api/app/
├── models/
│   ├── company.py            # NEW — Company ORM (branches relationship)
│   └── organization.py       # EDIT — add company_id column + company relationship
├── schemas/
│   ├── company.py            # NEW — CompanyCreate/Update/Response (+branch_count)
│   └── organization.py       # EDIT — accept name/city/region/address/company_id
├── services/
│   ├── company_service.py    # NEW — CRUD + list_branches_grouped_by_city
│   └── organization_service.py # EDIT — persist new fields, optional company filter
├── api/
│   ├── auth.py               # NEW — POST /api/auth/login, /logout, GET /me
│   ├── deps.py               # NEW — get_current_user, require_admin (session-cookie)
│   ├── companies.py          # NEW — CRUD + /companies/{id}/branches grouped by city
│   └── organizations.py      # EDIT — guard writes, accept new fields, ?company_id filter
├── core/
│   ├── security.py           # REUSE — bcrypt verify_password (unchanged)
│   └── config.py             # EDIT — CORS allow_credentials + explicit origin (fallback)
└── main.py                   # EDIT — include auth + companies routers

apps/api/alembic/versions/
└── 0008_companies.py         # NEW — companies table + organizations.company_id (down_revision 0007_response_first_seen)

apps/api/tests/
├── test_auth.py              # NEW — login success/failure, /me, logout
├── test_rbac.py              # NEW — admin write vs review_operator read-only
├── test_company_service.py   # NEW — CRUD + grouping
└── test_organization_company.py # NEW — create/update persists company_id/city

apps/web/
├── next.config.ts            # EDIT — rewrites() /api/:path* -> API base
├── tailwind.config.js        # EDIT — dark palette from prototype :root vars
├── middleware.ts             # NEW — redirect unauth dashboard routes to /login
├── app/
│   ├── globals.css           # EDIT — prototype CSS variables + fonts
│   ├── login/page.tsx        # NEW — dark login form
│   └── (dashboard)/
│       ├── layout.tsx        # NEW — shell + server-side /me guard
│       ├── companies/page.tsx           # NEW — company list + create
│       └── companies/[id]/page.tsx      # NEW — branches grouped by city + add-branch modal
├── components/
│   ├── shell/sidebar.tsx     # NEW — prototype sidebar nav
│   ├── shell/topbar.tsx      # NEW — prototype topbar + user card
│   ├── company-form.tsx      # NEW — create/edit company
│   └── branch-form.tsx       # NEW — add/edit branch (name, city, url, address, mode)
├── lib/
│   ├── api.ts                # EDIT — relative /api + credentials:"include" + login/logout/getMe + company methods
│   └── types.ts              # EDIT — add Company; extend Organization (city/region/company_id)
```

**Structure Decision**: Web-application monorepo (existing). Backend follows the strict `api → services → models/schemas` layering already in place; the new auth surface lives in `api/auth.py` + `api/deps.py` and does not touch the scraper or analysis layers. Frontend introduces an `(dashboard)` route group so the authenticated shell wraps management pages while `/login` stays outside it. Existing `/organizations`, `/reviews`, `/scrape-runs`, `/http-scraper` are folded under the shell nav without behavior change.

## Key Design Decisions

1. **Company parent, existing org = Branch.** Rather than rebuild `organizations` into a new `branches` table (which would move the reviews FK and break the dedup contract), add a `companies` parent and a nullable `organizations.company_id`. The org row remains the scrape/dedup unit; "Branch/Филиал" is a UI relabel only. Lowest risk, satisfies Principle VII additive rule.

2. **City as an attribute, not an entity.** Grouping uses the existing `organizations.city` text column; grouping happens in `company_service.list_branches_grouped_by_city` and the UI. No `cities` table (YAGNI, Principle V).

3. **Reuse feature-004 session auth; no JWT.** `/api/auth/login` verifies via `core/security.verify_password` and sets `request.session["user_id"]`/`["role"]` on the already-mounted `SessionMiddleware`. `get_current_user` reads the session; `require_admin` enforces write RBAC. One auth system (Principle VII), no new dependency.

4. **Same-origin `/api` rewrite for cookies.** Next.js `rewrites()` proxy `/api/:path*` to the API so the browser talks to the web origin and the session cookie flows without cross-site friction. `lib/api` switches to relative `/api` paths + `credentials:"include"`. Fallback if rewrite is undesirable: `allow_credentials` + explicit CORS origin + `SameSite=Lax`.

5. **Write-only auth surface in v1.** Guard management writes (companies CRUD, org create/update/delete) with the auth dependency; leave existing public read endpoints unguarded to avoid breaking current pages. Full read-side lockdown is a documented follow-up.

6. **Migration chains from `0007_response_first_seen`.** After rebasing onto the updated main (007 merged), `0008_companies` sets `down_revision = "0007_response_first_seen"` — single linear chain, single alembic head.

## Complexity Tracking

No constitution violations — table intentionally empty. All changes are additive (one table, one nullable FK, new routers/deps/pages) and reuse existing auth, dedup, and scraper paths.

## Delivery Milestones

1. **Data backbone**: migration `0008_companies`, `Company` model, `organizations.company_id`, schemas — `alembic upgrade head` clean.
2. **Auth surface**: `api/auth.py` + `api/deps.py`, register router; auth + RBAC tests green.
3. **Company/Branch API**: `company_service`, `api/companies.py` (CRUD + grouped-by-city), extend org create/update + guards; contract tests green.
4. **Panel shell + auth wiring**: dark design system, sidebar/topbar, `/api` rewrite, `lib/api` credentials + auth methods, `/login`, middleware + server guard.
5. **Management pages**: `/companies` list + `/companies/[id]` branches-by-city + add-branch modal; existing views folded under shell.
6. **Verify**: pytest (incl. unchanged dedup regression), lint, manual login → create company → add branch → collect reviews on the branch.
