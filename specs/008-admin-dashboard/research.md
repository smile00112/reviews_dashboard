# Phase 0 Research: Admin Control Panel

All Technical Context items were resolved during exploration + a user decision round; no NEEDS CLARIFICATION remain.

## Decision 1 — Company/Branch data model

- **Decision**: Add a `companies` parent table and a nullable `organizations.company_id` FK. Keep the existing `organizations` row as the branch/scrape-point; relabel as «Филиал» in the UI only.
- **Rationale**: The org row already carries `city`, `region`, `address`, and the maps URL, and reviews dedup per-org via `uq_review_org_hash`. Introducing a separate `branches` table would move the reviews FK and the dedup unit, violating the frozen dedup contract (Principle VII/VIII). A parent + nullable FK is fully additive.
- **Alternatives considered**: (a) New `branches` table owning reviews — rejected: breaks dedup contract, large migration, high risk. (b) Rename `organizations`→`branches` + add `organizations` parent — rejected: churns `OrganizationService`, all routers, `admin/views.py`, `User.default_location_id`, `ScrapeRun.organization_id`.

## Decision 2 — City grouping

- **Decision**: Group by the existing `organizations.city` text column; grouping computed in service + UI.
- **Rationale**: Cities are a display grouping over tens of branches; a normalized catalog adds tables and joins with no MVP value (Principle V).
- **Alternatives considered**: A `cities` reference table — rejected as premature.

## Decision 3 — Authentication

- **Decision**: Reuse feature-004 auth: `users` table, `UserRole`, bcrypt (`core/security`), and the already-mounted `SessionMiddleware` (secret `ADMIN_SECRET_KEY`). Add `/api/auth/login|logout|me` and a `get_current_user` / `require_admin` dependency. No JWT, no new library.
- **Rationale**: Constitution v1.4.0 forbids a second auth system; the session mechanism already exists and is signed. Login just verifies the password and populates the session used by both sqladmin and the new API.
- **Alternatives considered**: JWT bearer (new token infra, dual identity) — rejected by constitution + user choice. NextAuth (new dependency, second store) — rejected.

## Decision 4 — Cross-origin cookies

- **Decision**: Add a Next.js `rewrites()` proxy so `/api/:path*` is served from the web origin; `lib/api` uses relative `/api` paths with `credentials:"include"`. Session cookie is then same-origin.
- **Rationale**: Avoids cross-site cookie/`SameSite` pitfalls between web:3000 and api:8000 with the least config.
- **Alternatives considered**: CORS `allow_credentials` + explicit origin + `SameSite=Lax` — kept as documented fallback if a proxy is undesirable.

## Decision 5 — Auth coverage in v1

- **Decision**: Guard only management/write routes (companies CRUD, org create/update/delete) with the auth dependency; leave existing public read endpoints open.
- **Rationale**: Protects the new mutating surface without breaking the current unauthenticated read pages; full read lockdown is a low-risk follow-up.
- **Alternatives considered**: Lock all endpoints now — rejected: would break existing `/organizations`, `/reviews` pages until they carry sessions; out of v1 scope.

## Decision 6 — Frontend styling

- **Decision**: Port the prototype's `:root` dark palette into `tailwind.config.js` `theme.extend.colors` + `globals.css`; load Fraunces/Manrope/JetBrains Mono via `next/font/google`; build `sidebar`/`topbar` shell components from the prototype markup.
- **Rationale**: Matches the approved look with Tailwind already in the stack; no UI component library needed.
- **Alternatives considered**: shadcn/radix/MUI — rejected: unnecessary dependency for a CRUD panel.

## Migration ordering note

Feature 007 (`0007_response_first_seen`) was merged into `main` before integration; `0008_companies.down_revision = "0007_response_first_seen"` — single linear chain, single head.
