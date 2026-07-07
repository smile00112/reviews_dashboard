# Contract: Organizations API extensions (branch fields + guards)

The existing `organizations` endpoints are the **Branch** CRUD. This feature extends the create/update payloads and guards the write routes. Existing read endpoints and response fields stay backward-compatible (new fields are additive).

## Schema additions

`OrganizationCreate` (currently `yandex_url`, `preferred_scrape_mode`) gains optional:
`name`, `city`, `region`, `address`, `company_id`.

`OrganizationUpdate` (currently `name`, `preferred_scrape_mode`) gains optional:
`city`, `region`, `address`, `company_id`.

`OrganizationResponse` gains: `city`, `region`, `company_id` (all nullable). Existing fields unchanged.

**Validation**: when `company_id` is provided it MUST reference an existing company (else `422`/`404`). When creating a branch under a company, `city` and a maps URL MUST be present (FR-015). `build_review_hash` inputs are NOT affected by any of these fields.

## Guards (RBAC)

| Route | Guard |
|-------|-------|
| `POST /api/organizations` | `require_admin` |
| `PATCH /api/organizations/{id}` | `require_admin` |
| `DELETE /api/organizations/{id}` | `require_admin` |
| `GET /api/organizations`, `GET /api/organizations/{id}` | unchanged (open in v1; read) |
| `POST /api/organizations/{id}/scrape`, `POST /api/scrape/all` | unchanged in v1 |

## Optional filter

`GET /api/organizations?company_id={id}` → only branches of that company (additive query param; omitted = all, as today).

## Test expectations

- Create org with `company_id` + `city` → persisted; appears in that company's grouped branches.
- Update org `city` → moves city group; update `company_id` → reassigns/unassigns.
- POST/PATCH/DELETE without admin session → 401/403.
- Existing dedup + scrape-result persistence tests unchanged and green (regression gate).
