# Feature 008 — Multi-provider map links in the UI + scrape-mode sync

**Date:** 2026-07-09
**Status:** Approved design, ready for implementation plan

## Goal

Surface and edit the additive `twogis_url` / `google_url` columns (feature 008) in the
web dashboard, and bring the frontend scrape-mode list into sync with the backend.

The provider links are **display / reference only**: they never feed the scrape URL
(`ScrapeService` still scrapes `yandex_url`) and never feed the dedup `content_hash`.
This matches the migration `0008_org_map_links` docstring.

## Context (current state)

- Backend `ScrapeMode` enum already has all 5 modes: `public`, `operator_auth`,
  `public_http`, `scrapeops`, `twogis_api`.
- `OrganizationResponse` already returns `twogis_url` / `google_url`.
- Migrations `0008_org_map_links` (adds the two columns) and `0009_seed_sushi_master`
  (seeds ~209 Sushi Master points, each its own `organizations` row, with the two links
  attached where matched) are the in-progress WIP.
- **Frontend is behind the backend:** `lib/types.ts` `ScrapeMode` lists only 3 of 5
  modes and the `Organization` type is missing the two link fields; `mode-select.tsx`
  offers only 3 modes; the table and detail page do not show or edit the links.

Data model: each point is its own `organizations` row; `yandex_url` is the primary
scrape URL (`preferred_scrape_mode = public`); `twogis_url` / `google_url` are secondary
reference links on the same row.

## Scope

### Backend (`apps/api`)

- `schemas/organization.py` — `OrganizationUpdate`: add
  `twogis_url: str | None = None`, `google_url: str | None = None`.
  (`OrganizationResponse` already exposes them.)
- `services/organization_service.py::update` — apply the two links using
  `data.model_fields_set` (field presence), NOT the existing `is not None` pattern, so
  that an explicitly-provided empty value **clears** the link (`null`) while an absent
  field leaves it unchanged. Normalize empty string `""` to `None`.
- `OrganizationCreate` — unchanged. Links are set by editing the org, not on creation
  (the create form is Yandex-URL-focused; YAGNI).

### Frontend (`apps/web`)

- `lib/types.ts` — `ScrapeMode` add `"scrapeops" | "twogis_api"`; `Organization` add
  `twogis_url: string | null` and `google_url: string | null`.
- `components/mode-select.tsx` — offer all 5 modes.
- `lib/api.ts` — extend the `updateOrganization` payload type with optional
  `twogis_url` / `google_url`.
- `components/organizations-table.tsx` — new "Карты" column: compact clickable badges
  **Я / 2ГИС / G**; a missing link renders as a disabled grey badge with no `href`.
- `app/organizations/[id]/page.tsx` — a "Ссылки на карты" block showing the three links
  plus a small inline edit form for `twogis_url` / `google_url`. Extract the editor into
  a new client component `components/org-links-editor.tsx` so the page stays thin.

## Error handling / edge cases

- Empty input saves `null` (clears the link), not an empty string.
- Light URL validation: any non-empty string is accepted (seed data mixes
  `go.2gis.com/...`, `maps.app.goo.gl/...`, `yandex.by/...`). `type="url"` gives a browser
  hint but does not block.
- A failed PATCH shows an inline error message under the form (existing pattern in
  `organization-form.tsx`).
- Table badges: no link → inactive grey badge without `href`.

## Testing

- **Backend (constitution-required org API contract):** a test that
  `PATCH /api/organizations/{id}` with `twogis_url` / `google_url` persists and returns
  them; that an explicit empty value clears a link; and that an absent field leaves it
  unchanged.
- **Frontend:** `npm run lint`. E2E not extended (heavy, needs a running stack);
  verified manually via `npm run dev`.

## Explicitly out of scope

- Wiring the `twogis_api` scrape mode to `twogis_url` (chosen: display-only).
- Editing links in the create form.
- A separate `specs/008-*` Spec Kit spec (none exists; this work started migration-first).
  This design doc is the record.
