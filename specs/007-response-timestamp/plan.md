# Implementation Plan: Review Response Timestamp

**Branch**: `feature/007-response-timestamp` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-response-timestamp/spec.md`

## Summary

Add one nullable timestamp, `response_first_seen_at`, to the `reviews` table. It is stamped exactly once — the moment `ReviewService.upsert_reviews` first persists a non-empty `response_text` for a review — and is immutable thereafter. The response is already parsed and stored for both Yandex (`parser.py`) and 2GIS (`twogis_api.py`); this feature only records *when we first saw it*, using the run's collection time (`now`) already computed in `upsert_reviews` — the same observation-time proxy the product uses for `first_seen_at`. No new parsing, no new endpoint, no web changes. `response_text` stays excluded from the dedup hash, so review identity is unaffected.

## Technical Context

**Language/Version**: Python 3.12 (API).

**Primary Dependencies**: existing FastAPI, SQLAlchemy, Alembic, Pydantic. No new dependencies.

**Storage**: PostgreSQL 16 (SQLite for tests via `JSON().with_variant` pattern already in models). **One nullable column added**: `reviews.response_first_seen_at TIMESTAMPTZ NULL` (Alembic `add_column`). No new tables, no enum changes, no backfill.

**Testing**: pytest. New tests over `ReviewService.upsert_reviews` covering the null→present stamp, immutability across re-scrape, empty-when-no-response, and dedup-unaffected. Mirrors `tests/test_review_deduplication.py`.

**Target Platform**: same Docker Compose stack; no browser involvement.

**Project Type**: Web application monorepo (`apps/api` + `apps/web`); this feature touches `apps/api` only.

**Performance Goals**: none affected — one extra column write on the existing upsert path.

**Constraints**: Read-only; additive column only; timestamp immutable once set; must not alter `build_review_hash` inputs; identical behavior across providers.

**Scale/Scope**: same internal tool scale (~tens of orgs, thousands of reviews).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ Pass | Storing/displaying visible business responses is in scope; this adds metadata about an already-collected field. No excluded capability (replies/LLM/notifications) touched. |
| II. Read-Only Review Collection | ✅ Pass | Records an observation timestamp only; never publishes/edits/deletes a reply. Stored response stays display-only. |
| III. Critical-Path Testing | ✅ Pass | New tests cover the persistence logic (stamp-once, immutability) and prove dedup/hash is unaffected — exactly the data-loss/duplicate risk class the constitution requires covering. |
| IV. Scraper Reliability & Debuggability | ✅ Pass | Scrape-run records unchanged; no new failure modes; absence of a response is not treated as deletion. |
| V. Simplicity (YAGNI) | ✅ Pass | One nullable column + a conditional in existing upsert. No new service, table, endpoint, or migration machinery beyond `add_column`. Rejected `response_last_seen_at`/edit-detection as unneeded. |
| VI. Deterministic Local Analytics | ✅ Pass | Analytics fields/flow untouched; timestamp is not an analysis input and never feeds the dedup hash. |
| VII. Admin Panel Security | ✅ Pass | No admin/auth surface changes; additive read-only column. |
| VIII. Multi-Provider Collection | ✅ Pass | Logic lives in the shared `upsert_reviews` off the standard `ParsedReview.response_text`; works identically for Yandex + 2GIS with zero provider-specific branching. |

**Post-design re-check**: All gates pass. No Complexity Tracking entries required. No constitution amendment needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-response-timestamp/
├── spec.md
├── plan.md
├── data-model.md
├── tasks.md              # /speckit-tasks output
└── checklists/
    └── requirements.md
```

### Source Code (additions to existing layout)

```text
apps/api/
├── app/
│   ├── models/review.py                 # add response_first_seen_at column
│   ├── services/review_service.py       # stamp-once logic in upsert_reviews
│   └── schemas/review.py                # expose response_first_seen_at on ReviewResponse
├── alembic/versions/
│   └── 0007_response_first_seen.py      # NEW add_column migration (down_revision 0006_twogis_api_mode)
└── tests/
    └── test_response_timestamp.py       # NEW stamp-once / immutability / dedup-unaffected tests
```

**Structure Decision**: All logic sits in the existing `ReviewService.upsert_reviews`, which every provider already funnels through (Principle VIII). The stamp is derived from the `now` value the method already computes, so no signature or interface changes ripple outward. The column mirrors the existing `first_seen_at`/`last_seen_at` timestamp columns in style (`DateTime(timezone=True)`), differing only in being nullable with no server default.

## Key Design Decisions

1. **Stamp off the existing `now`**: `upsert_reviews` already computes a single per-call `now`. Reuse it so the review's own timestamps and the response timestamp share one time basis (the observation-time proxy). No new clock reads.
2. **Transition guard, not unconditional write**: current code overwrites `response_text` whenever the parsed value is truthy. Split into (a) null→present: set text **and** `response_first_seen_at=now`; (b) already-present: refresh text only, leave the timestamp. This is the single behavioral change and the whole immutability guarantee.
3. **Nullable, no server default, no backfill**: historical rows and unresponded reviews keep NULL truthfully (FR-003, FR-009). We never fabricate a first-seen time we didn't observe.
4. **Excluded from dedup hash (unchanged)**: `build_review_hash` inputs are untouched; a review gaining a response updates in place (FR-006). Guarded by a dedicated test.
5. **Provider-agnostic**: because the stamp reads `ParsedReview.response_text` inside the shared upsert, Yandex and 2GIS get identical behavior with no source branch (FR-007).
6. **API-only exposure**: add the field to `ReviewResponse`; no new endpoint, no web work (deferred per spec assumptions).
7. **IntegrityError race path left as-is**: the concurrent-insert fallback bumps `last_seen_at` only; the winning insert carries the stamp via the new-row path. Acceptable and simplest — documented, not special-cased.

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Delivery Milestones

1. **Schema** — model column + migration `0007`; `alembic upgrade head` clean. (US1 storage)
2. **Logic** — stamp-once transition guard in `upsert_reviews`; unit tests (stamp, immutability, empty, dedup-unaffected). (US1 core)
3. **API surface** — `response_first_seen_at` on `ReviewResponse`; verify via reviews endpoint. (US1 exposure)
