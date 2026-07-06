# Tasks: Review Response Timestamp

**Input**: Design documents from `/specs/007-response-timestamp/`

**Prerequisites**: plan.md, spec.md, data-model.md

**Organization**: Single P1 user story; tasks grouped by phase for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1)

## Phase 1: Setup

- [ ] T001 [US1] Add nullable column `response_first_seen_at = Column(DateTime(timezone=True), nullable=True)` to the `Review` model in `apps/api/app/models/review.py`, next to `response_text`. (`DateTime` is already imported.)
- [ ] T002 [US1] Create Alembic migration `apps/api/alembic/versions/0007_response_first_seen.py` with `revision = "0007_response_first_seen"`, `down_revision = "0006_twogis_api_mode"`; upgrade `op.add_column("reviews", sa.Column("response_first_seen_at", sa.DateTime(timezone=True), nullable=True))`; downgrade `op.drop_column("reviews", "response_first_seen_at")`. No backfill.

**Checkpoint**: column exists in model + migration; `alembic upgrade head` applies cleanly.

---

## Phase 2: User Story 1 — Operator sees when a response first appeared (Priority: P1) 🎯 MVP

**Goal**: `response_first_seen_at` is stamped once at the response null→present transition, immutable after, NULL when no response, identical for Yandex + 2GIS, and does not affect dedup.

**Independent Test**: Upsert a parsed review carrying a response → read it back through the reviews API → `response_first_seen_at` equals that run's time; re-upsert with an edited response → value unchanged; upsert a review without a response → value NULL.

### Core logic

- [ ] T003 [US1] In `ReviewService.upsert_reviews` (`apps/api/app/services/review_service.py`), **new-review path**: set `response_first_seen_at=now` on the `Review(...)` construction when `parsed.response_text` is truthy, else leave unset (NULL). Reuse the existing per-call `now`.
- [ ] T004 [US1] In the same method, **existing-review path**: replace the unconditional `if parsed.response_text: existing.response_text = ...` with a transition guard — if `parsed.response_text and not existing.response_text`: set both `existing.response_text` and `existing.response_first_seen_at = now`; elif `parsed.response_text`: refresh `existing.response_text` only, leave `response_first_seen_at` untouched. Never write the timestamp when it is already set. Leave the `IntegrityError` fallback (last_seen_at bump) as-is.

### API surface

- [ ] T005 [P] [US1] Add `response_first_seen_at: datetime | None = None` to `ReviewResponse` in `apps/api/app/schemas/review.py` (near `response_text`). `datetime` import + `from_attributes=True` already present — confirm import.

### Tests

- [ ] T006 [P] [US1] Create `apps/api/tests/test_response_timestamp.py` (mirror `tests/test_review_deduplication.py` setup) covering:
  - insert with response → `response_first_seen_at` set (non-NULL);
  - insert without response → NULL;
  - re-upsert adding a response to a previously response-less review → timestamp set on that run (not equal to `first_seen_at`);
  - re-upsert with response already present, text edited → `response_first_seen_at` unchanged (immutability);
  - dedup contract: adding a response updates in place, `build_review_hash` unchanged, 0 new rows inserted.

**Checkpoint**: all new tests pass; existing dedup tests still green; both providers exercise the shared path.

---

## Phase 3: Polish & Validation

- [ ] T007 [US1] Run `alembic upgrade head` against a local DB and confirm the column is added; run `pytest -v` (full suite) and `pytest tests/test_review_deduplication.py -v` — all green.
- [ ] T008 [US1] End-to-end sanity: upsert (or scrape) a review with a response, `GET /api/organizations/{id}/reviews`, confirm `response_first_seen_at` populated on responded reviews and NULL otherwise.

**Checkpoint**: migration applies, suite green, API surfaces the field correctly.

---

## Dependencies

- T001 → T002 (model column before migration).
- T001 → T003, T004 (attribute must exist before service writes it).
- T003, T004 before T006 (logic before its tests can pass).
- T005 independent of service logic ([P]).
- T007, T008 after all of Phase 1–2.
