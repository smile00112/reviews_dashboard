# Implementation Plan: 2GIS Review Collection (twogis_api mode)

**Feature**: `006-2gis-reviews` | **Spec**: [spec.md](./spec.md) | **Constitution**: v1.3.0

## Summary

Add a `twogis_api` scrape mode that collects 2GIS **org-level** reviews via 2GIS public
JSON APIs and persists them through the existing dedup/analytics pipeline. No HTML parsing
of 2GIS DOM; no captcha bypass. Direct API with a ScrapeOps proxy fallback for IP-blocks;
ScrapeOps is also required to resolve `go.2gis.com` short links to a firm id (2GIS bot-walls
the SPA shell from datacenter IPs).

## Tech Stack & Structure

Same stack as existing scrapers (FastAPI, `requests`, SQLAlchemy, Alembic). New files live
in the existing `apps/api/app/scraper/` layer; no new service or dependency.

- `apps/api/app/scraper/twogis_api.py` — `TwogisApiScraper` (new). Owns firm-id resolution,
  catalog lookup, reviews pagination, JSON→`ParsedReview` mapping, and the ScrapeOps fallback.
- `apps/api/app/models/enums.py` — add `ScrapeMode.twogis_api`.
- `apps/api/alembic/versions/0006_twogis_api_mode.py` — `ALTER TYPE scrape_mode_enum ADD VALUE`
  (mirror 0005; autocommit; Postgres-only).
- `apps/api/app/core/config.py` — 2GIS settings (catalog key, review key, limit, page size, delay).
- `apps/api/app/services/scrape_service.py` — pick `TwogisApiScraper` when `mode == twogis_api`.
- `apps/api/app/services/review_service.py` — derive `source`/`platform` from `scrape_mode`
  (`twogis_api` → `source="2gis"`, `platform=gis2`) so provenance is correct; hash inputs unchanged.
- `apps/api/tests/test_twogis_api.py` — mapping, dedup parity, blocked-key → needs_manual_action,
  firm-id-from-URL vs short-link.

## Data Flow

```
scrape(url)
  ├─ firm_id = _resolve_firm_id(url)
  │     • url has /firm/{id}      → regex, no network
  │     • go.2gis.com/CODE short  → ScrapeOps HTML → dominant /firm/{id}
  ├─ org_id, org_meta = _catalog_lookup(firm_id)   # catalog.api.2gis.com/3.0/items/byid
  │     • direct GET (ScrapeOps fallback on 403/network)
  │     • 403 apiKeyIsBlocked → needs_manual_action
  ├─ reviews = _fetch_reviews(org_id)              # public-api.reviews.2gis.com/3.0/orgs/{id}/reviews
  │     • paginate offset += page_size until limit or no meta.next_link
  │     • direct GET (ScrapeOps fallback), map JSON → ParsedReview
  └─ ScrapeResult(organization=ParsedOrganization(name,rating,review_count), reviews)
```

## JSON → ParsedReview mapping

| ParsedReview field   | 2GIS source                          |
|----------------------|--------------------------------------|
| `author_name`        | `user.name`                          |
| `rating`             | `int(rating or 0)`                   |
| `review_text`        | `text or ""`                         |
| `review_date_text`   | `date_created` (immutable → stable hash) |
| `review_date`        | `normalize_review_date(date_created[:10])` |
| `response_text`      | `official_answer.text` (display-only) |
| `external_review_id` | `id`                                 |

`build_review_hash` is called unchanged by `upsert_reviews`; the mapping feeds it the same
four fields it always uses. 2GIS provenance is carried by `scrape_mode`/`source`/`platform`,
none of which are hash inputs.

## Constitution Check

- **I. Scope** — 2GIS is in scope as of v1.3.0 (this amendment). ✅
- **II. Read-only** — API is read-only; `official_answer` stored display-only. ✅
- **III. Testing** — dedup, mapping, and mode-contract tests added. ✅
- **IV. Debuggability** — every run yields a `ScrapeRun`; blocked key / bot wall →
  `needs_manual_action` with artifact; no silent retry/bypass. ✅
- **V. Simplicity** — no new service/queue; reuses `requests`, existing persistence. ✅
- **VI. Analytics** — unchanged; runs after hash, additive. ✅
- **VIII. Multi-provider** — standard `ScrapeResult` + `upsert_reviews`; keys in settings;
  no hash branching; ScrapeOps key redacted from errors. ✅

**Complexity Tracking**: none — no deviation from the simplest multi-provider approach.

## Risks

- Public 2GIS keys could be rotated/blocked upstream → mitigated by settings-configurable
  keys and `needs_manual_action` on block.
- Short-link resolution depends on ScrapeOps → full `/firm/{id}` URLs need no proxy;
  documented as the recommended input.
- 2GIS reviews are org-level (not branch) → documented; branch filtering is future work.
