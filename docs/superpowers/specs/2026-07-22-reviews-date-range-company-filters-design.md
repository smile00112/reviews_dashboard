# Reviews page: date-range period + company filter

Date: 2026-07-22

## Goal

On `/reviews`, add two filters, reusing the `/overview` (feature 013) patterns:

1. **Период → произвольный диапазон** — a custom date range in addition to the existing preset chips.
2. **Бренды (company)** — a single-select company filter that also narrows the location list to that brand's organizations.

## Current state

- `GET /api/reviews` and `GET /api/reviews/summary` already accept `date_from` / `date_to`
  (filtering `Review.review_date`) and a `period` preset (`24h|7d|30d|year`). Neither accepts `company_id`.
- The reviews page (`apps/web/app/(dashboard)/reviews/page.tsx`) reads only `period` from the URL;
  `ReviewFilters` renders 4 preset chips and a single `<select>` over all orgs.
- `/overview` already has `DateRangePicker` and a company dropdown that narrows branches by
  `org.company_id` — reuse both.

## Design

### Backend
- Add `company_id: UUID | None` to `list_reviews` and `reviews_summary` (`api/reviews.py`), forwarded
  to the service methods.
- `ReviewService.list_global` / `.summary`: apply a company filter via a scalar subquery
  `Review.organization_id.in_(select(Organization.id).where(Organization.company_id == company_id))`.
  A subquery (not an extra join) keeps row counts clean. No new `period` token — `date_from`/`date_to`
  are already independent params.

### Frontend (`/reviews`)
- **Custom range:** add `DateRangePicker` after the preset chips in `ReviewFilters`. Picking a preset
  sends `period` and clears `from`/`to`; applying a range sends `date_from`/`date_to` and clears
  `period`. All state lives in the URL (mirroring overview). Malformed/inverted dates fall back to no
  range.
- **Company filter:** add a single-select "Бренды" `<details>` dropdown (overview pattern). Selecting a
  brand:
  - narrows the location `<select>` options to that brand's orgs,
  - clears `organization_id` if it no longer belongs to the brand,
  - sends `company_id` to `/api/reviews` and `/api/reviews/summary`.
- Location control stays **single-select** (unchanged from today) — only its option list is narrowed.

## Decisions

- Location filter remains single-select for reviews-page consistency (overview uses multi-select).
- `period` preset filters on `coalesce(review_date, first_seen_at)`; custom range filters on
  `review_date` — accepted, matches existing endpoint behavior.

## Out of scope

- Aspects panel / summary unaffected beyond the new params.
- No migration, no new dependency.

## Verification

- `pytest -v` in `apps/api` (add a test covering `company_id` filtering on `/api/reviews`).
- `npm run lint` in `apps/web`.
