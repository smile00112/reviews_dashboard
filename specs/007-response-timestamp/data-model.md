# Data Model: Review Response Timestamp

## Modified Entity: Review (`reviews` table)

One additive column. No other columns, constraints, or indexes change.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `response_first_seen_at` | `TIMESTAMPTZ` (`DateTime(timezone=True)`) | **YES** | none (no server default) | Collection-run time at which a non-empty `response_text` was **first** persisted for this review. NULL until then; immutable once set. |

### Relationship to existing columns

- `first_seen_at` (existing): when the **review** was first observed. Unchanged — already serves as the review's creation-time proxy.
- `last_seen_at` (existing): bumped every run. Unchanged.
- `response_text` (existing): the business reply text. Unchanged in storage; the write path gains a transition guard (below).
- `content_hash` (existing): dedup identity. **`response_first_seen_at` and `response_text` remain excluded** from `build_review_hash`.
- `reply_text` / `reply_at` (feature 004, admin-authored): **unrelated**. This feature never touches them; `response_first_seen_at` is about the *scraped* response, not operator replies.

## State Transitions (`response_first_seen_at`)

```
              review inserted / updated by upsert_reviews(run_time = now)

  [no stored response]  --response seen this run-->  set response_first_seen_at = now   (stamp once)
  [no stored response]  --no response this run--->   response_first_seen_at stays NULL
  [response stored]     --same/edited response--->   response_first_seen_at UNCHANGED   (immutable)
  [response stored]     --no response this run--->    response_first_seen_at UNCHANGED   (retained; absence ≠ deletion)
```

Invariants:
- Set at most once per review, exactly at the NULL→non-NULL transition of `response_text`.
- Never cleared, never moved, once set.
- `response_first_seen_at IS NULL` ⟺ review has never had a stored response (including all pre-feature rows — no backfill).

## Validation Rules (from spec)

- FR-002/FR-005: no write to `response_first_seen_at` when the review already has a stored response.
- FR-004: value equals the current run's `now`, not the review's `first_seen_at`.
- FR-006: change does not affect `build_review_hash` → no re-insert of an existing review.
- FR-009: migration adds the column nullable with no default and performs no data backfill.

## Migration

`alembic/versions/0007_response_first_seen.py`, `down_revision = "0006_twogis_api_mode"`:
- **upgrade**: `add_column("reviews", Column("response_first_seen_at", DateTime(timezone=True), nullable=True))`.
- **downgrade**: `drop_column("reviews", "response_first_seen_at")`.

## API Exposure

`ReviewResponse` (schemas/review.py) gains `response_first_seen_at: datetime | None = None`, populated via `from_attributes`. No new endpoint; surfaced through existing reviews listing/detail responses.
