# Phase 1 Data Model: Admin Control Panel

Additive only. One new table (`companies`) and one new nullable column (`organizations.company_id`). **No change to `reviews`, `content_hash`, `uq_review_org_hash`, or scraper tables.**

## Entity: Company (NEW — table `companies`)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK, default uuid4 | |
| `name` | Text | NOT NULL | Display name (Организация) |
| `is_active` | Boolean | NOT NULL, server_default true | Soft on/off; not deleted |
| `created_at` | timestamptz | NOT NULL, server_default now | |
| `updated_at` | timestamptz | NOT NULL, server_default now, onupdate now | |

**Relationships**: `branches` → one-to-many `Organization` via `Organization.company_id` (`back_populates="company"`). No cascade delete — deleting a company sets child `company_id` to NULL (see FK below).

**Validation**: `name` required, non-empty (schema-level, min_length 1).

## Entity: Organization (EDIT — table `organizations`, "Branch/Филиал" in UI)

Existing columns unchanged. Added:

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `company_id` | UUID | NULL, FK → `companies.id` ON DELETE SET NULL, indexed | Which company this branch belongs to; NULL = unassigned |

Existing columns reused as branch attributes: `name`, `city`, `region`, `address`, `yandex_url`/`normalized_url`/`external_id` (maps source), `preferred_scrape_mode`, `rating`, `review_count`, `last_scrape_status`. The dedup/scrape columns and `reviews`/`scrape_runs` relationships are untouched.

**Validation (schema-level, additive to create/update)**: for a branch created under a company, `city` and a maps URL are required (FR-015); `company_id` if provided MUST reference an existing company.

## Entity: User (EXISTING — unchanged)

Reused as-is: `id`, `name`, `email` (unique), `role` (`UserRole`: `admin` | `review_operator`), `is_active`, `password_hash` (bcrypt), `default_location_id` → `organizations.id`. No schema change.

## Entity: Review (EXISTING — unchanged)

`organization_id` FK and `uq_review_org_hash (organization_id, content_hash)` remain the dedup unit. A "branch" == an `organizations` row, so review collection/dedup is unaffected.

## Migration `0008_companies.py`

- `down_revision = "0007_response_first_seen"` (chains from the current main head).
- Upgrade:
  1. `create_table("companies", ...)` — columns above; PK on `id`.
  2. `op.add_column("organizations", sa.Column("company_id", <UUID>, nullable=True))`.
  3. `op.create_foreign_key("fk_organizations_company_id", "organizations", "companies", ["company_id"], ["id"], ondelete="SET NULL")`.
  4. `op.create_index("ix_organizations_company_id", "organizations", ["company_id"])`.
- Downgrade: drop index, FK, column, then `drop_table("companies")`.
- Follow the idempotent/portable patterns in `0004_admin_rbac.py` (UUID type handling for Postgres vs SQLite test backend).

## Derived view: branches grouped by city

`CompanyService.list_branches_grouped_by_city(company_id)` returns an ordered mapping `{ city (or "Без города"): [Organization, ...] }` built from `organizations` where `company_id == company_id`, ordered by city then name. No storage; computed on read.
