# Feature Specification: Admin Control Panel (auth + Company/Branch management)

**Feature Branch**: `feature/008-admin-dashboard`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: "Custom dark control panel (styled after the dashboard prototype) with login and an admin cabinet, reusing the existing admin auth. Admins add Organizations (a new Company parent entity) and their Branches (филиалы). A Branch is the existing organization scrape point (has a maps URL + city); branches are grouped by city under a company. Reviews/dedup/scraper flow unchanged. Scope v1: login, admin cabinet, Company/Branch CRUD; analytics deferred. RBAC: admin = full CRUD, review_operator = read-only."

## Context

The operator team currently manages tracked map-points as a flat list — each point is a single Yandex/2GIS scrape source with a maps URL and a city. There is no way to group these points under a parent business, and the only management surface is a fixed-look internal admin table with no branded experience. Operators need a styled, authenticated control panel where they can sign in and organize the points they track as **Organizations (companies) → Branches (филиалы) grouped by city**, so a franchise or multi-location business reads as one entity with its per-city points beneath it. Review collection, deduplication, and scraping behavior are already solved and MUST NOT change; this feature only adds the grouping entity and the authenticated management UI on top of the existing data.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator signs in to the control panel (Priority: P1)

An operator opens the control panel and is required to authenticate before seeing any management data. After entering valid credentials they land in the admin cabinet; invalid credentials are rejected with a clear message. Any attempt to reach a management page while signed out redirects to the login screen.

**Why this priority**: Without an auth gate the panel exposes all managed data and controls in a shared internal environment. It is the precondition for every other story.

**Independent Test**: Visit any management URL while signed out → redirected to login. Enter valid credentials → reach the cabinet. Enter invalid credentials → stay on login with an error. Sign out → management URLs redirect to login again.

**Acceptance Scenarios**:

1. **Given** a registered operator, **When** they submit valid credentials on the login screen, **Then** they are signed in and see the admin cabinet.
2. **Given** a signed-out visitor, **When** they open a management page directly, **Then** they are redirected to the login screen.
3. **Given** wrong credentials, **When** submitted, **Then** login is refused with a non-revealing error and no session is created.
4. **Given** a signed-in operator, **When** they sign out, **Then** their session ends and protected pages redirect to login.

---

### User Story 2 - Admin creates an Organization (company) (Priority: P1)

A signed-in admin opens the Organizations section, creates a new company by name, and sees it appear in the list. The company starts with no branches.

**Why this priority**: The company is the parent container every branch attaches to; branch management is impossible without it.

**Independent Test**: As an admin, create a company "Coffee Co", confirm it appears in the list and its detail view shows zero branches.

**Acceptance Scenarios**:

1. **Given** an admin in the Organizations section, **When** they submit a company name, **Then** the company is created and shown in the list.
2. **Given** a created company, **When** the admin opens it, **Then** its detail view shows the company and an empty branch list grouped by city.
3. **Given** an admin edits or removes a company, **When** they confirm, **Then** the change is reflected and branches of a removed company become unassigned (not deleted).

---

### User Story 3 - Admin adds Branches (филиалы) grouped by city (Priority: P1)

Inside a company, an admin adds a branch by giving it a name, a city, a maps URL (the scrape source), and optional address/scrape mode. The new branch appears under its city heading in the company's branch list. Adding another branch in the same city groups it under the same heading; a branch in a new city creates a new city group.

**Why this priority**: This is the core value — turning the flat scrape-point list into an Organization→city→branch structure operators can navigate.

**Independent Test**: In "Coffee Co", add a branch "Тверская, 17" in Москва with a maps URL, then add "Невский, 88" in СПб. Confirm two city groups appear (Москва, СПб) each containing its branch.

**Acceptance Scenarios**:

1. **Given** an admin viewing a company, **When** they add a branch with a name, city, and maps URL, **Then** the branch is created, attached to the company, and listed under its city.
2. **Given** two branches in the same city, **When** both are added, **Then** they appear under a single city heading.
3. **Given** a branch is created, **When** an operator later triggers collection for it, **Then** reviews are collected and deduplicated for that branch exactly as before this feature (no change to collection behavior).
4. **Given** an admin edits a branch's city, **When** saved, **Then** it moves to the correct city group.
5. **Given** an admin removes a branch, **When** confirmed, **Then** it disappears from the company and its previously collected reviews follow the existing deletion behavior for a scrape point.

---

### User Story 4 - Read-only operator is prevented from changing data (Priority: P2)

A user with the read-only role can sign in and browse organizations and branches but cannot create, edit, or delete companies or branches; those controls are unavailable and any direct attempt is refused.

**Why this priority**: Enforces the two-role policy already defined for the panel; important but the panel is usable for the primary admin without it.

**Independent Test**: Sign in as a read-only operator; confirm create/edit/delete controls are absent and a direct write attempt is refused, while lists remain viewable.

**Acceptance Scenarios**:

1. **Given** a read-only operator, **When** they view Organizations, **Then** they see the data but no create/edit/delete controls.
2. **Given** a read-only operator, **When** a write action is attempted directly, **Then** it is refused and no data changes.

---

### User Story 5 - Operator navigates existing views within the new panel (Priority: P3)

The existing review, scrape-history, and scraper-session views remain reachable inside the new control-panel shell so the operator has one consistent, signed-in place to work.

**Why this priority**: Continuity and polish; the underlying views already exist and are unchanged.

**Independent Test**: From the cabinet, navigate to reviews and scrape history and confirm they load within the panel shell.

**Acceptance Scenarios**:

1. **Given** a signed-in operator, **When** they use the panel navigation, **Then** existing review/history views open within the same shell.

---

### Edge Cases

- What happens when an admin creates a branch without selecting a city? → City is required for a branch; creation is refused with a validation message.
- What happens to existing scrape points that predate companies? → They remain valid and unassigned (no company); they can be viewed and later attached to a company.
- What happens when a company is deleted that still has branches? → Branches are unassigned, not deleted; their reviews are untouched.
- What happens when two branches in a company share the same maps URL? → Allowed at the company level, but each branch keeps the existing per-point uniqueness for its reviews; no change to dedup behavior.
- What happens when a session expires while editing? → The next action redirects to login; unsaved input is not persisted.
- What happens when a read-only operator crafts a direct write request? → Refused with an authorization error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The control panel MUST require authentication before any management view or data is accessible; unauthenticated access MUST redirect to a login screen.
- **FR-002**: The system MUST authenticate operators using the existing internal user accounts, roles, and password protection — no separate or parallel account system MUST be introduced.
- **FR-003**: The system MUST support signing out, ending the session so protected views are no longer accessible.
- **FR-004**: Admin users MUST be able to create, view, edit, and delete Organizations (companies), identified by a name.
- **FR-005**: Admin users MUST be able to add a Branch to a company, providing at least a name, a city, and a maps URL (the collection source); address and preferred collection mode MAY be provided.
- **FR-006**: The system MUST group a company's branches by city in the company view.
- **FR-007**: Admin users MUST be able to edit and delete branches, including moving a branch to a different city.
- **FR-008**: Deleting a company MUST NOT delete its branches or their reviews; affected branches MUST become unassigned from any company.
- **FR-009**: Read-only operators MUST be able to view organizations and branches but MUST NOT be able to create, edit, or delete companies or branches; the system MUST refuse such write attempts.
- **FR-010**: A branch MUST correspond to an existing scrape point, so that collecting reviews for a branch reuses the current collection and deduplication behavior unchanged.
- **FR-011**: The system MUST NOT alter review collection, the deduplication rule, normalization, or scraper behavior as part of this feature.
- **FR-012**: Existing scrape points created before this feature MUST remain valid without a company and MUST be viewable in the panel.
- **FR-013**: The control panel MUST present the branded, dark visual style of the approved dashboard prototype for its shell (navigation, header, forms).
- **FR-014**: Existing review, scrape-history, and scraper-session views MUST remain accessible within the control-panel shell.
- **FR-015**: Branch creation MUST validate that a city and a maps URL are present before the branch is saved.

### Key Entities *(include if feature involves data)*

- **User (existing)**: An operator account with a role (`admin` or `review_operator`) and protected credentials; reused unchanged for panel sign-in and authorization.
- **Company (new)**: A parent business/organization that groups branches. Key attributes: name, active flag, timestamps. Has many branches.
- **Branch (existing scrape point, relabelled)**: A single map-point that reviews are collected for. Key attributes reused from today's scrape point: name, city, maps URL, address, collection mode, rating/counts. Newly may belong to one company.
- **City (grouping attribute)**: The city label carried on a branch; used to group branches within a company. Not a standalone managed record in this feature.
- **Review (existing)**: Unchanged. Belongs to a branch (today's scrape point); collection and deduplication behavior are untouched.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of management pages are inaccessible without a valid session (every protected route redirects to login when signed out).
- **SC-002**: An admin can create a company and add its first branch (with city and maps URL) in under 2 minutes without assistance.
- **SC-003**: A company with branches in multiple cities displays every branch under exactly one correct city group, with no branch missing or duplicated.
- **SC-004**: Read-only operators complete 0 successful write actions on companies or branches (all such attempts refused).
- **SC-005**: After the feature ships, review collection and deduplication produce the same results as before for an unchanged scrape point (existing collection/dedup tests pass unchanged).
- **SC-006**: A newly added branch can have reviews collected for it successfully on the first attempt using the existing collection trigger.

## Assumptions

- The existing internal user accounts, roles (`admin`, `review_operator`), password hashing, and session mechanism from the prior admin-panel feature are reused for the control panel; no new auth system is built.
- "Organization" in the user's request maps to the new **Company** parent entity; the existing organization record is the **Branch** (scrape point) and is relabelled in the UI only — it is not renamed or restructured in storage.
- City is a free-text/selected label on a branch (reusing the existing city field); a normalized city catalog is out of scope.
- v1 covers login, the admin cabinet, and Company/Branch CRUD in the prototype shell. The prototype's analytics screens (KPIs, charts, review feeds, competitors) are deferred to a later feature.
- Google Maps and any third map provider remain out of scope; branches use the existing supported providers (Yandex, 2GIS).
- The panel targets a small internal operator team (tens of organizations), not public or high-concurrency use.
