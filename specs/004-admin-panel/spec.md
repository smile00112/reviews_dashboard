# Feature Specification: Admin Panel with Authentication and RBAC

**Feature Branch**: `feature/004-admin-panel`

**Created**: 2026-07-01

**Status**: Draft

**Input**: User description: "Feature 004: Admin Panel with Authentication and RBAC. Internal SQLAdmin panel mounted at /admin on existing FastAPI app. Two roles: admin (full CRUD on organizations, reviews, users) and review_operator (read organizations, read+edit reviews, no user management). Auth via email+password with bcrypt hashes, session middleware, secrets from env. Scope: install sqladmin+passlib, create User model, extend Organization/Review models with admin-needed fields, RBAC views, seed script. Out of scope: custom frontend dashboard, other map providers, posting replies."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Secure Login to Admin Panel (Priority: P1)

An operator or administrator navigates to `/admin`, is redirected to the login page,
enters their email and password, and gains access to the panel with the appropriate
role-limited view. Inactive accounts cannot log in.

**Why this priority**: Without authentication the panel is inaccessible; every other
story depends on a working login.

**Independent Test**: Open `/admin` in a browser → redirected to `/admin/login`. Submit
valid credentials → land on the admin dashboard. Submit wrong password → error shown.
Submit credentials for inactive account → error shown.

**Acceptance Scenarios**:

1. **Given** an unauthenticated user, **When** they visit `/admin`, **Then** they are
   redirected to the login page.
2. **Given** an active admin with correct email/password, **When** they submit the login
   form, **Then** they are granted access and see all three sections (Organizations,
   Reviews, Users).
3. **Given** any user with incorrect password, **When** they submit the login form,
   **Then** they see an error and remain on the login page.
4. **Given** an inactive user with correct credentials, **When** they submit the login
   form, **Then** they are denied access with an appropriate error.
5. **Given** a logged-in user, **When** they click Logout, **Then** their session is
   invalidated and they are redirected to the login page.

---

### User Story 2 — Administrator Manages Organizations, Reviews, and Users (Priority: P2)

An administrator logs in and can create, view, edit, and delete any Organization,
Review, or User record directly from the admin panel with search, filter, and sort
controls.

**Why this priority**: The admin role is the primary management interface for the
operator team lead.

**Independent Test**: Log in as admin → navigate to each section → verify CRUD actions
are available and functional for Organizations, Reviews, and Users.

**Acceptance Scenarios**:

1. **Given** an admin user, **When** they open the Organizations section, **Then** they
   see a list with search, filters, sort, and Create/Edit/Delete buttons.
2. **Given** an admin user, **When** they open the Reviews section, **Then** they can
   filter by platform, status, rating, and paid flag, and perform full CRUD.
3. **Given** an admin user, **When** they open the Users section, **Then** they can
   create, edit (change role/is_active), and delete users.

---

### User Story 3 — Review Operator Manages Reviews Within Role Limits (Priority: P2)

A review_operator logs in and can view organizations (read-only), edit review fields
(reply text, status, paid flag), but cannot create or delete reviews, and cannot see
the Users section at all.

**Why this priority**: Operators need to respond to and triage reviews without risking
data loss or accessing user management.

**Independent Test**: Log in as review_operator → check sidebar: Users section absent;
Organizations present but no edit/create/delete; Reviews present with edit allowed but
no create/delete buttons.

**Acceptance Scenarios**:

1. **Given** a review_operator, **When** they navigate to `/admin`, **Then** the Users
   section is not visible in the navigation.
2. **Given** a review_operator, **When** they view the Organizations list, **Then** no
   Create, Edit, or Delete actions are available.
3. **Given** a review_operator, **When** they view a Review detail page, **Then** they
   can edit `reply_text`, `status`, and `is_paid` fields and save successfully.
4. **Given** a review_operator, **When** they attempt to create or delete a review via
   direct URL, **Then** they are denied access (redirected to login or shown
   permission error).

---

### User Story 4 — View Organizations with Search and Filters (Priority: P3)

Any authorized user can search organizations by name or city, filter by region and
franchise status, and sort by name or creation date, enabling rapid navigation of a
multi-location network.

**Why this priority**: Navigability is important but secondary to access control.

**Independent Test**: Log in → open Organizations → use search box → apply
city/region/franchise filter → change sort order → verify results update correctly.

**Acceptance Scenarios**:

1. **Given** any logged-in user, **When** they type in the search box, **Then** results
   filter to organizations matching name or city.
2. **Given** any logged-in user, **When** they apply a "franchise" filter, **Then** only
   franchise organizations are shown.

---

### User Story 5 — View Reviews with Search, Filters, and Sort (Priority: P3)

Any authorized user can search reviews by author name or text, filter by platform,
status, rating, or paid flag, and sort by creation date (descending by default).

**Why this priority**: Review navigation is core to daily operator work.

**Independent Test**: Log in → open Reviews → search by author name → filter by
status=new → sort by rating → verify results.

**Acceptance Scenarios**:

1. **Given** any logged-in user, **When** they filter Reviews by status "new", **Then**
   only reviews with status "new" are displayed.
2. **Given** any logged-in user, **When** they sort by created_at descending, **Then**
   the most recent reviews appear first.

---

### User Story 6 — Seed Initial Users via Script (Priority: P4)

A developer running first-time setup can execute a CLI script to create one admin and
one review_operator user with passwords supplied as arguments or environment variables.
Re-running the script does not create duplicates.

**Why this priority**: Required for initial setup but not user-facing.

**Independent Test**: Run seed script twice with the same credentials → check the DB
has exactly one admin and one operator → verify passwords are stored as hashes.

**Acceptance Scenarios**:

1. **Given** an empty users table, **When** the seed script runs with valid args, **Then**
   two users are created with hashed passwords.
2. **Given** existing users in the DB, **When** the seed script runs again, **Then** no
   duplicate users are created (idempotent).

---

### Edge Cases

- What happens when the `ADMIN_SECRET_KEY` environment variable is missing at startup?
  → Application fails to start with a clear configuration error (not a silent default).
- What happens if a logged-in user's `is_active` flag is set to `false` mid-session?
  → On next request, `authenticate()` finds the account inactive and invalidates the
  session, forcing re-login.
- What happens if a review_operator tries to POST to a create-review URL directly?
  → `is_accessible` or `can_create` check returns False and the panel denies access.
- What if the seed script is given an already-taken email?
  → It skips insertion (idempotent) and exits successfully without error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST require authentication before displaying any admin view;
  unauthenticated requests to `/admin/*` MUST redirect to the login page.
- **FR-002**: System MUST authenticate users by email and bcrypt-hashed password; login
  MUST fail for wrong password or inactive account.
- **FR-003**: System MUST store a user's role in their session; every view access check
  MUST read the role from the session without a DB round-trip.
- **FR-004**: System MUST allow users to log out; logout MUST clear the session and
  redirect to the login page.
- **FR-005**: The `admin` role MUST have full Create/Read/Update/Delete access to
  Organizations, Reviews, and Users.
- **FR-006**: The `review_operator` role MUST have read-only access to Organizations
  (no Create/Edit/Delete).
- **FR-007**: The `review_operator` role MUST be able to edit the `reply_text`,
  `status`, and `is_paid` fields of a Review, but MUST NOT be able to create, delete,
  or edit `paid_cost`/`paid_marked_by_user_id` fields (those are admin-only).
- **FR-008**: The Users section MUST be hidden from (not accessible by) the
  `review_operator` role.
- **FR-009**: Organizations list MUST support search by name and city, filters by
  region and franchise status, and sorting by name and created_at.
- **FR-010**: Reviews list MUST support search by author name and review text, filters
  by platform/status/rating/is_paid, and default sort by created_at descending.
- **FR-011**: Admin panel session secret MUST be read from environment variable
  `ADMIN_SECRET_KEY`; application MUST NOT start if this variable is unset or empty.
- **FR-012**: A seed script MUST create an initial admin user and review_operator user
  with passwords supplied via environment variables or CLI args, and MUST be
  idempotent.
- **FR-013**: Password hashes MUST use bcrypt; plaintext passwords MUST NOT be stored
  or logged anywhere.
- **FR-014**: The admin panel MUST be additive — existing API routes and scraper
  behaviour MUST remain unchanged.

### Key Entities

- **User**: An operator team member with an email (unique), a role (admin or
  review_operator), an active flag, and a stored password hash. A user may be
  associated with a default organization.
- **Organization**: A network location (already exists); needs a city/region/address
  and franchise flag surfaced in the admin view.
- **Review**: A collected Yandex review (already exists); needs status, is_paid,
  platform fields for admin triage workflow.
- **AdminSession**: A server-side session binding a User to their authenticated request
  context; holds user_id and role only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can log in and reach the admin dashboard in under 5 seconds on
  a local network connection.
- **SC-002**: All RBAC rules pass automated tests — 100% of defined access-control
  scenarios are covered and green.
- **SC-003**: A developer can set up initial users from zero to working login in under
  2 minutes using the seed script.
- **SC-004**: The application starts cleanly (no import errors, no migration failures)
  after each implementation phase is applied to a clean database.
- **SC-005**: A review_operator cannot access any restricted action (create review,
  delete review, edit organization, view users) via any URL or form submission.

## Assumptions

- The admin panel is for internal use only; there is no public registration flow.
- Session cookies are sufficient for auth; no JWT or OAuth2 is needed.
- SQLAdmin's default UI is acceptable; no custom theme beyond the dark-mode CSS
  variables from `docs/plans/dashboard_prototype.html` needs to be injected at this
  stage. (Custom theming is a separate task.)
- The existing `Organization` and `Review` SQLAlchemy models will be extended with
  additive nullable columns (city, region, is_franchise, status, is_paid, platform)
  via Alembic migration; no existing column will be renamed or dropped.
- The `review_operator` role cannot edit an organization's name or Yandex URL; those
  fields are admin-only.
- Passwords for seed users will be supplied via `ADMIN_PASSWORD` and `OPERATOR_PASSWORD`
  environment variables when running the seed script.
- The `review_operator` can mark a review as `is_paid` but cannot set `paid_cost`.
  (Assumption — admin plan §2 does not detail paid_cost edit rights per role.)

## Clarifications

### Session 2026-07-01

- Q: What is the session expiry time? → A: 12 hours (SESSION_MAX_AGE=43200 seconds),
  configurable via env var `SESSION_MAX_AGE`. No default hardcoded in source.
- Q: Which review fields can review_operator edit? → A: `reply_text`, `status`, `is_paid`
  only. Fields `paid_cost` and `paid_marked_by_user_id` are admin-only.
- Q: What happens when ADMIN_SECRET_KEY is missing at startup? → A: pydantic-settings
  raises a validation error at process start — application does not start silently.
- Q: Are city/region columns already in the Organization model? → A: No. The current
  Organization model only has `name`, `yandex_url`, `address`. Fields `city`, `region`,
  and `is_franchise` must be added via an additive Alembic migration (nullable, no
  existing data lost).
- Q: What are the allowed values for Review.status? → A: Enum with four values:
  `new`, `in_progress`, `answered`, `escalated` (matches admin_panel_plan.md §3).
- Q: What platforms does the Review.platform field support? → A: Single value `yandex`
  for this iteration. Enum is defined as extensible (`yandex | google | gis2`) per plan
  §3, but only `yandex` is populated by the current scraper.
- Q: How are seed user passwords supplied? → A: Via environment variables `ADMIN_PASSWORD`
  and `OPERATOR_PASSWORD` read by `scripts/seed_users.py`. Passwords never appear in
  source code or logs.
