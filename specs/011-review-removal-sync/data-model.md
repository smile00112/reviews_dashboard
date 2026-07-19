# Data Model: Review Removal Sync

All changes are additive (constitution: dedup contract frozen, ORM changes additive-only).

## Review (`reviews`) — modified

| Field | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `removed_at` | `timestamptz` | yes | `NULL` | NULL = currently present on platform. Set to detection time by removal marking (full pass only). Cleared (`NULL`) whenever the review is seen again. **Never** feeds `content_hash`. |

State transitions:

```text
present (removed_at IS NULL)
  └─ full pass, hash not seen, guards pass ──▶ removed (removed_at = now)
removed
  └─ any pass sees the hash again (upsert update path) ──▶ present (removed_at = NULL, last_seen_at = now)
```

Invariants:
- Removal marking scope: `organization_id = pass.org AND platform = pass.platform AND removed_at IS NULL`.
- Never deleted; identity/dedup (`content_hash`, `uq_review_org_hash`) unchanged.
- Guard: a full pass with 0 seen reviews and ≥1 non-removed row marks nothing unless `Organization.<platform>_review_count == 0`.

## ScrapeRun (`scrape_runs`) — modified

| Field | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `full_pass` | `boolean` | no | `false` | True only when coverage is corroborated: scraper proved end-of-list (pagination exhausted; no cap hit; no skipped page) AND the pass saw ≥ the org's stored platform counter (guards against the Yandex ~600-review `?page=N` ceiling). Historical rows read as partial — correct. |

## Job (`jobs`) — options key added (no schema change)

`Job.options` (existing JSON) gains optional key:

| Key | Type | Constraint | Meaning |
|---|---|---|---|
| `force_full_every_days` | int | ≥ 1 when present | When counters match, still run a full pass if the org's latest `success AND full_pass` scrape run (in the platform's job mode) is absent or older than N days. Absent/0 ⇒ feature off. |

## ScrapeResult (in-memory dataclass, `scraper/types.py`) — modified

| Field | Type | Default | Notes |
|---|---|---|---|
| `full_pass` | `bool` | `False` | Set by paginating scrapers on proven exhaustion. Playwright scroll modes never set it. Default false = "coverage unknown ⇒ partial" safe rule. |

## Migration

`0016_review_removal_tracking.py`:
- `ALTER TABLE reviews ADD COLUMN removed_at timestamptz NULL`
- `ALTER TABLE scrape_runs ADD COLUMN full_pass boolean NOT NULL DEFAULT false`
- No data backfill; no index (count/list filters ride existing `ix_reviews_org_platform` at tens-of-orgs scale).
- Downgrade drops both columns.

## Derived queries

- Job comparison count: `SELECT count(*) FROM reviews WHERE organization_id=:o AND platform=:p AND removed_at IS NULL`.
- Last full pass (R6): `SELECT max(finished_at) FROM scrape_runs WHERE organization_id=:o AND mode=:platform_mode AND status='success' AND full_pass`.
- Removal marking: `UPDATE reviews SET removed_at=:now WHERE organization_id=:o AND platform=:p AND removed_at IS NULL AND content_hash NOT IN (:seen)`.
