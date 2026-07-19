# API Contract Deltas: Review Removal Sync

Only deltas listed; everything else is unchanged. No new endpoints.

## Review responses (all endpoints returning reviews)

Added field:

```json
{
  "removed_at": "2026-07-19T04:12:33Z"  // or null = present on platform
}
```

## `GET /api/organizations/{id}/reviews` and global feed listing

New query param:

| Param | Values | Default | Meaning |
|---|---|---|---|
| `removed` | `active` \| `removed` \| `all` | `active` | `active` excludes removed reviews (new default — behavior change: removed rows disappear from default lists); `removed` returns only removed; `all` returns both. |

Invalid value → `422`.

## Scrape run responses (`GET /api/scrape/runs...`, run detail)

Added field:

```json
{
  "full_pass": false  // true = coverage corroborated (pagination exhausted AND seen >= platform counter); removal marking was allowed
}
```

## `PATCH /api/jobs/{id}` (existing, admin-only)

`options` JSON accepts a new optional key:

```json
{ "options": { "delay_seconds": 2, "force_full_every_days": 7 } }
```

Validation: integer ≥ 1 when present; `422` otherwise. Absent ⇒ forced refresh disabled.

## Job run item payload / reasons (informational contract for UI)

`payload` for a reviews-job item now reports `platform_total` vs non-removed `scraped_before`; new/changed human-readable reasons:

- scrape triggered: counters differ in either direction (lower counter no longer skips);
- skip: "counters match" (computed over non-removed reviews only);
- scrape triggered: "forced full refresh" when `force_full_every_days` fires;
- failure `error_code="empty_full_pass"`: full pass returned zero reviews while non-removed reviews exist and the platform counter is not 0.

## Scrape run failure codes

New `error_code` value: `empty_full_pass` (run status `failed`, no data changes made).
