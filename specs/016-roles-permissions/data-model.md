# Data Model: Roles & Permissions System (feature 016)

## Entities

### Role (`roles` table)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK, default uuid4 |
| `name` | Text | display name, **unique**, non-empty (e.g. "Администратор", "Колл-центр", "Менеджер") |
| `slug` | Text | stable machine key, **unique** (e.g. `admin`, `call_center`, `manager`) |
| `is_system` | Boolean | not null, default false; `true` only for `admin` |
| `description` | Text | nullable |
| `created_at` | DateTime(tz) | server_default now() |

- Relationship: `permissions` → `list[RolePermission]`, `cascade="all, delete-orphan"`.
- Relationship: `users` → `list[User]` (back-populates `User.role`).
- Invariants (enforced in `RoleService`):
  - `is_system` role (`admin`) cannot be deleted, renamed, or have grants edited.
  - A role with ≥1 assigned user cannot be deleted (→ 409).
  - `name` unique + non-empty; `slug` unique (auto-derived from name on create, or supplied).

### RolePermission (`role_permissions` table)

| Column | Type | Notes |
|--------|------|-------|
| `role_id` | UUID | FK → `roles.id` (`ON DELETE CASCADE`), not null |
| `permission` | Text | catalog key, not null |
| | | **UNIQUE(`role_id`, `permission`)** |

- A row = "role is granted this permission". No row = denied.
- No rows are stored for the `admin` system role (D2 shortcut).
- `permission` must be a member of the catalog (validated in service; unknown → 422/400).

### User (`users` table) — modified

| Column | Change |
|--------|--------|
| `role_id` | **NEW** UUID FK → `roles.id` (`ON DELETE RESTRICT`), not null after backfill |
| `role` | **RETAINED, made nullable** (legacy `user_role_enum`); unused post-migration, kept for rollback |

- Relationship: `role` → `Role`.
- Exactly one role per user (FR-005); `role_id` NOT NULL enforces it after migration.

## Permission Catalog (code — `core/permissions.py`)

Static, not user-editable. Single source of truth for validation, the `/catalog` endpoint,
and default seed grants.

**Pages** (`PAGE_PERMISSIONS`): `page:overview`, `page:ratings`, `page:companies`,
`page:organizations`, `page:reviews`, `page:scrape_runs`, `page:jobs`,
`page:attention_rules`, `page:http_scraper`, `page:settings`, `page:roles`.

**Actions** (`ACTION_PERMISSIONS`): `action:org.manage`, `action:company.manage`,
`action:scrape.run`, `action:job.manage`, `action:review.edit_status`,
`action:attention.manage`, `action:settings.edit`, `action:scraper_session.manage`,
`action:users.manage`, `action:roles.manage`.

`ALL_PERMISSIONS = PAGE_PERMISSIONS + ACTION_PERMISSIONS` (21). Each entry carries a
human label (RU) + category for the matrix UI.

## Route → permission mapping (replaces current `require_admin`)

| Router / endpoint | New guard |
|-------------------|-----------|
| `organizations.py` create/update/delete | `action:org.manage` |
| `companies.py` create/update/delete | `action:company.manage` |
| `scrape_runs.py` create/trigger | `action:scrape.run` |
| `scraper_sessions.py` login/session ops | `action:scraper_session.manage` |
| `jobs.py` run / update | `action:job.manage` |
| `reviews.py` PATCH (status/escalate) | `action:review.edit_status` |
| `attention_rules.py` create/update/delete/restart | `action:attention.manage` |
| `settings.py` write | `action:settings.edit` |
| `roles.py` all CRUD/grant | `action:roles.manage` |
| (future) user management | `action:users.manage` |
| dashboard/read endpoints (`get_current_user`) | unchanged (auth-only; page gating on FE + optional `page:*` server check) |

Page-view gating is primarily a frontend concern (nav + server-component check via
`/api/auth/me`); the **data** behind each page is already read-only under `get_current_user`,
so `page:*` permissions gate navigation/entry, while `action:*` permissions gate mutations at
the API — this is the FR-015/FR-018 division (backend authoritative for actions; pages gated
at entry).

## Effective-permission resolution (`PermissionService`)

```
effective_permissions(user) ->
  if user.role.is_system and user.role.slug == "admin": return ALL_PERMISSIONS
  else: return { rp.permission for rp in user.role.permissions }

has_permission(user, perm) -> perm in effective_permissions(user)
```

## Seeded rows (migration 0024)

| slug | name | is_system | default grants |
|------|------|-----------|----------------|
| `admin` | Администратор | true | (none stored — full via shortcut) |
| `call_center` | Колл-центр | false | `page:overview, page:ratings, page:reviews, action:review.edit_status` |
| `manager` | Менеджер | false | `page:overview, page:ratings, page:companies, page:organizations, page:reviews, page:scrape_runs, page:jobs, page:attention_rules` |

User mapping: `users.role == 'admin' → role_id(admin)`, `== 'review_operator' → role_id(call_center)`.

## State / lifecycle

Roles have no status field — they exist or not. `is_system` is set once at seed and never
changes. Grants toggle freely for non-system roles. Deletion is gated by the in-use check.
