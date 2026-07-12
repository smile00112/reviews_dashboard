# Data Model: Backend Hardening (010)

All changes additive; dedup contract (`build_review_hash`, `uq_review_org_hash`) untouched.

## Review (`reviews`)

No column changes. New indexes (migration `0013`, mirrored in `Review.__table_args__` for SQLite tests):

| Index | Columns | Serves |
|---|---|---|
| `ix_reviews_org_review_date` | (organization_id, review_date) | list ordering `review_date DESC` per org |
| `ix_reviews_org_first_seen` | (organization_id, first_seen_at) | `new_only` cutoff, dashboard period filters |
| `ix_reviews_org_platform` | (organization_id, platform) | dashboard platform filtering |

## ScrapeRun (`scrape_runs`)

No schema changes. **Semantics change** (parent/bulk runs):

- Parent terminal status derived from children:
  - all children `failed` → `failed`
  - no `success`, ≥1 `needs_manual_action` → `needs_manual_action`
  - ≥1 `success` (or zero children) → `success`
- `reviews_seen/inserted/updated` on parent = sums over children.
- Child runs unchanged (individually terminal, one per organization).

State transitions unchanged: `queued → running → {success | failed | needs_manual_action}`.

## ScraperSession (`scraper_sessions`)

- `SessionStatus` enum gains value **`pending`** (Postgres: `ALTER TYPE session_status_enum ADD VALUE 'pending'` in migration 0013; SQLite: string column, no-op).
- Transitions:
  - `* → pending` when login/check is scheduled
  - `pending → valid | needs_manual_action | expired | missing` when background work finishes
  - While `pending`, `get_session_status()` file heuristics MUST NOT overwrite the status; a second login/check request while `pending` is a no-op returning current state.

## RatingSnapshot (`rating_snapshots`)

No schema changes. Access pattern change: overview batch-loads earliest in-period snapshot per (organization_id, platform) in one grouped/window query instead of per-org queries.

## Counters contract (FR-002)

For every run: `reviews_inserted` = rows actually inserted and committed; `reviews_updated` = existing rows touched (map hit or collision recovery); `reviews_seen` = parsed reviews offered to persistence (2GIS sub-1-rating reviews are dropped at mapping time and never reach persistence, so they do not count).
