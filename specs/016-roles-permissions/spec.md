# Feature Specification: Roles & Permissions System

**Feature Branch**: `016-roles-permissions`

**Created**: 2026-07-22

**Status**: Draft

**Input**: User description: "нужно сделать систему ролей. пока вижу три роли: админ, колл центр, менеджер. сделай страницу настроек, где ролям можно давать доступ к страницам. при проектировании заложи возможность ограничивать показ каких то элементов интерфейса и выполнять какие либо действия (например ответ на отзыв)"

## Overview

Today the control panel recognises exactly two hard-coded roles (`admin` and
`review_operator`) and its access control is effectively binary (admin / not-admin), baked
into code. Operators cannot shape who sees which page or who may perform which action
without a code change.

This feature replaces the fixed two-role model with an **admin-managed, configurable
role/permission system**. An administrator defines roles and, through a settings page,
grants each role access to specific **pages** and specific **actions**. Access is enforced
by the backend (the source of truth) and mirrored by the interface for a clean experience.
Three roles are seeded to start — **Administrator**, **Call Center**, **Manager** — and the
administrator may create more.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Grant a role access to pages (Priority: P1)

An administrator opens a "Roles & Access" settings page, picks the **Call Center** role, and
ticks which pages that role may open (e.g. Overview, Reviews, Ratings). After saving, every
user with that role sees exactly those pages in navigation and can open only those pages;
all other pages are hidden and refused if accessed directly.

**Why this priority**: This is the core promise of the feature — assigning page access per
role from a UI — and delivers standalone value even without action-level control.

**Independent Test**: Sign in as admin, grant Call Center access to a subset of pages, sign
in as a Call Center user, confirm navigation shows only the granted pages and that opening a
non-granted page URL directly is refused.

**Acceptance Scenarios**:

1. **Given** the admin is on the Roles & Access page, **When** they grant the Call Center
   role access to the Reviews page and save, **Then** a Call Center user sees "Reviews" in
   navigation and can open it.
2. **Given** the Call Center role lacks access to the Jobs page, **When** a Call Center user
   navigates directly to the Jobs page URL, **Then** access is refused and the page content
   is not returned.
3. **Given** a page grant is removed from a role and saved, **When** a user of that role
   reloads, **Then** the page disappears from their navigation and can no longer be opened.

### User Story 2 - Restrict actions within a page (Priority: P1)

An administrator grants the **Manager** role access to the Reviews page but does **not** grant
the "edit review status" action. A Manager can open Reviews and read them, but the controls
that change a review's status are hidden, and any attempt to perform that change is refused.

**Why this priority**: Page access alone is insufficient — the operator explicitly asked to
be able to restrict *actions* (e.g. modifying a review), not just page visibility. Page-view
and action control together are the minimum viable feature.

**Independent Test**: Grant a role page access without a specific action permission, sign in
as that role, confirm the action's controls are hidden and that invoking the action is
refused with an authorization error.

**Acceptance Scenarios**:

1. **Given** the Manager role has Reviews page access but not the edit-status action, **When**
   a Manager opens a review, **Then** the status-editing controls are not shown.
2. **Given** the same role, **When** a status change is submitted anyway (e.g. via a direct
   request), **Then** the system refuses it with an authorization error and the review is
   unchanged.
3. **Given** the admin later grants the edit-status action to Manager, **When** a Manager
   reloads, **Then** the status controls appear and the change succeeds.

### User Story 3 - Manage custom roles (Priority: P2)

An administrator creates a new role (e.g. "Аналитик"), gives it a name and a set of page and
action grants, later renames it, and eventually deletes it. Deletion is refused while any
user is still assigned to it, and the built-in Administrator role can never be modified or
deleted.

**Why this priority**: Beyond the three seeded roles, the operator wants the freedom to model
their team. Important, but the three seeded roles already deliver value without it.

**Independent Test**: As admin, create a role, assign grants, rename it, attempt to delete it
while a user holds it (refused), reassign that user, then delete it (succeeds).

**Acceptance Scenarios**:

1. **Given** the admin is on Roles & Access, **When** they create a role with a name and a
   set of grants, **Then** the role appears in the matrix and can be assigned to users.
2. **Given** a role is assigned to at least one user, **When** the admin tries to delete it,
   **Then** deletion is refused with a clear "role is in use" message.
3. **Given** the built-in Administrator role, **When** the admin views it, **Then** it cannot
   be deleted, renamed, or have any permission removed.

### User Story 4 - Existing users keep working after upgrade (Priority: P1)

When the feature is deployed, every existing user retains equivalent access with no manual
intervention: current administrators remain full-access administrators, and current
read-oriented operators land on a role with a sensible, comparable set of grants.

**Why this priority**: A migration that locks people out or silently escalates privileges is
the highest-impact failure mode; continuity is mandatory.

**Independent Test**: With pre-existing admin and operator accounts, deploy the feature and
confirm the admin still has full access and the operator has the mapped role's access — no
account is left without a role.

**Acceptance Scenarios**:

1. **Given** a pre-existing administrator account, **When** the feature is deployed, **Then**
   that account has the immutable Administrator role and full access.
2. **Given** a pre-existing read-oriented operator account, **When** the feature is deployed,
   **Then** that account is assigned the Call Center role with its default grants.
3. **Given** any pre-existing account, **When** the feature is deployed, **Then** it has
   exactly one role and is never left role-less.

### Edge Cases

- **Last administrator protection**: The Administrator role cannot be deleted; because a role
  in use cannot be deleted and Administrator is also `is_system`, the system can never be left
  without a functioning admin path.
- **Signed-in user's access changes mid-session**: When an admin changes a role's grants, the
  affected users' effective permissions update on their next request/reload; no stale grant is
  honored by the backend even if the interface still shows a control.
- **Direct access attempt to a hidden page or action**: Hiding a control in the interface is
  never the only defense — the backend refuses the page or action regardless of what the
  interface displays.
- **Unauthenticated request**: A request with no valid session is refused as unauthenticated
  (distinct from an authenticated-but-unauthorized refusal).
- **Duplicate or empty role name**: Creating a role with a blank or already-used name is
  refused with a validation message.
- **Unknown permission in a grant request**: A request to grant a permission that is not in
  the system's known catalog is refused.
- **A role with no grants**: A user whose role has zero page grants can sign in but sees an
  empty navigation and cannot open any gated page — this is allowed, not an error.
- **Reply-to-provider is not offered**: Posting or editing replies on a provider is not a
  grantable action and never appears in the permission catalog (out of scope, read-only).

## Requirements *(mandatory)*

### Functional Requirements

**Roles**

- **FR-001**: The system MUST support multiple named roles, seeded initially with three:
  Administrator, Call Center, and Manager.
- **FR-002**: An administrator MUST be able to create, rename, and delete roles through a
  dedicated "Roles & Access" settings page.
- **FR-003**: The system MUST designate the Administrator role as a built-in role that always
  has full access and cannot be deleted, renamed, or have any permission revoked.
- **FR-004**: The system MUST refuse to delete a role that is currently assigned to one or
  more users, returning a clear "role in use" conflict.
- **FR-005**: Every user MUST have exactly one role at all times; no user may be left without
  a role.
- **FR-006**: Role names MUST be unique and non-empty; the system MUST refuse duplicates and
  blanks.

**Permissions catalog**

- **FR-007**: The system MUST define a fixed catalog of permissions in two categories: **page**
  permissions (one per control-panel page) and **action** permissions (one per gated
  operation).
- **FR-008**: Page permissions MUST cover each control-panel page: Overview, Ratings,
  Companies, Organizations, Reviews, Scrape Runs, Jobs, Attention Rules, HTTP Scraper,
  Settings, and Roles & Access.
- **FR-009**: Action permissions MUST cover, at minimum: manage organizations, manage
  companies, run a scrape, manage jobs, edit a review's status, manage attention rules, edit
  settings, manage the scraper session, manage users, and manage roles.
- **FR-010**: The permission catalog MUST NOT include any permission for posting or editing
  replies on a provider (out of scope; read-only principle).
- **FR-011**: The system MUST refuse a grant request that references a permission outside the
  known catalog.

**Assignment & the matrix UI**

- **FR-012**: The Roles & Access page MUST present an editable matrix of roles against
  permissions, with the permissions visibly grouped into "Pages" and "Actions".
- **FR-013**: An administrator MUST be able to grant or revoke any individual permission for
  any non-built-in role and save the change.
- **FR-014**: Absence of a grant MUST mean "denied"; only explicitly granted permissions are
  allowed (except the built-in Administrator, which is always fully allowed).

**Enforcement**

- **FR-015**: The backend MUST be the authoritative enforcement point: every gated page and
  every gated action MUST be refused server-side when the caller's role lacks the required
  permission.
- **FR-016**: An authenticated caller lacking a required permission MUST receive an
  authorization-denied response; a caller with no valid session MUST receive an
  authentication-required response — the two MUST be distinguishable.
- **FR-017**: The interface MUST hide navigation entries, buttons, and other elements a user
  lacks permission for, sourcing the user's effective permission set from the backend.
- **FR-018**: Interface hiding MUST be treated as convenience only and MUST NOT be the sole
  enforcement; the backend MUST refuse the underlying request regardless of interface state.
- **FR-019**: The system MUST expose the signed-in user's role and effective permission set so
  the interface can mirror access decisions.

**Continuity & compatibility**

- **FR-020**: On deployment, existing administrator accounts MUST map to the Administrator
  role and existing read-oriented operator accounts MUST map to the Call Center role, with no
  account left role-less.
- **FR-021**: The seeded Call Center and Manager roles MUST each receive a sensible default set
  of grants at deployment.
- **FR-022**: The change MUST preserve the single existing sign-in mechanism; no second,
  parallel authentication system may be introduced.
- **FR-023**: The separate low-level administration panel MUST continue to gate its own access
  on whether the signed-in user holds the Administrator role.
- **FR-024**: The review deduplication behavior and the read-only collection principle MUST
  remain unchanged by this feature.

### Key Entities *(include if feature involves data)*

- **Role**: A named set of access grants. Attributes: a display name, a stable machine key, a
  built-in flag (immutable Administrator), and an optional description. A role is held by zero
  or more users.
- **Permission grant**: An association between a role and a single catalog permission, meaning
  "this role is allowed this page or action." Absence means denied.
- **Permission (catalog item)**: A fixed, known identifier belonging to either the Pages
  category or the Actions category. Defined by the system, not user-editable.
- **User**: An existing account that now references exactly one Role (replacing the previous
  fixed role value). Retains its existing identity and credentials.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can change which pages a role may access, and the change is
  reflected in that role's users' navigation and page access after a single reload — with no
  code change or redeploy.
- **SC-002**: 100% of pre-existing user accounts retain a role and equivalent access
  immediately after deployment, with zero accounts left role-less and zero unintended
  privilege escalations.
- **SC-003**: Every gated page and action is refused by the backend when attempted by a role
  without the corresponding permission, in 100% of tested allow/deny cases — even when the
  request bypasses the interface.
- **SC-004**: The built-in Administrator role cannot be deleted, renamed, or reduced in any
  attempted operation (100% of such attempts refused), and a role assigned to a user cannot be
  deleted.
- **SC-005**: An administrator can create a new role, assign it page and action grants, and
  hand it to a user who then experiences exactly that access — completed entirely through the
  settings interface.
- **SC-006**: No permission enabling replies to a provider is ever presented in the catalog or
  grantable to any role.

## Assumptions

- The existing session-based sign-in, credential store, and account records are reused; only
  the role representation changes (from a fixed value to a reference to a managed role).
- Permission checks resolve against the user's current role at request time; there is no
  caching that would honor a revoked grant after the change is saved.
- The permission catalog (which pages and which actions exist) is defined and maintained in
  the system, not authored by end users; administrators grant/revoke from that fixed catalog.
- Granularity is role-level and system-wide: permissions are not scoped per-organization or
  per-record in this feature (row-level scoping is out of scope).
- Only administrators (holders of the manage-roles action) may view and edit the Roles &
  Access page.
- The three seeded roles' default grants are: Administrator = everything; Call Center =
  read-oriented pages plus editing a review's status; Manager = read/analytics pages without
  user- or role-management. Exact default grants are refined during planning.
- The previous fixed role value is retained (unused, nullable) after migration to allow a safe
  rollback, and removed in a later change once the new model is proven.
- "Roles & Access" is a distinct page reached from the Settings area of navigation.
