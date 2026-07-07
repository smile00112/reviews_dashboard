# Feature Specification: Review Response Timestamp

**Feature Branch**: `feature/007-response-timestamp`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "Track when a review's business response was first observed by us. We already scrape and store response text for Yandex Maps and 2GIS reviews, but we have no timestamp for when that response appeared. Since neither platform exposes real creation timestamps for reviews or responses, use our own observation time (the moment a scrape first sees the content) as the proxy — the same rule already used for reviews. Add a nullable first-observed timestamp for the response that is stamped exactly once, when a review's response transitions from absent to present, and is immutable thereafter; it stays empty while a review has no response."

## Context

The dashboard collects and displays business responses (owner replies) to Yandex Maps and 2GIS reviews. The response text is already captured, but operators cannot tell *when* a reply appeared. Neither platform exposes a reliable creation timestamp for reviews or for responses, so — consistent with how the product already treats a review's own first-observed time — we approximate the response's appearance time with **our observation time**: the moment a scrape run first sees a response attached to a review.

This lets operators reason about responsiveness ("this review sat unanswered for two weeks after we first saw it") using data we can actually obtain, without claiming a precision the sources don't provide.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator sees when a response first appeared (Priority: P1)

An operator reviewing a business's reviews wants to know, for each review that has a reply, the approximate time that reply first showed up in our collected data, so they can judge how promptly the business responds.

**Why this priority**: This is the entire feature. Without the first-observed timestamp there is no new value; with it, every responded review carries an answerable "when did the reply appear" question. It is the MVP and the whole product slice.

**Independent Test**: Scrape (or upsert) a review that already carries a response, then read that review back through the reviews API; the review exposes a non-empty response-first-observed time equal to that collection run's time. Fully testable in isolation.

**Acceptance Scenarios**:

1. **Given** a review being collected for the first time that already has a business response, **When** the collection run persists it, **Then** the review records a response-first-observed time equal to that run's collection time.
2. **Given** a review being collected for the first time that has no business response, **When** the collection run persists it, **Then** the review's response-first-observed time is empty.
3. **Given** a previously stored review that had no response, **When** a later collection run first sees a response on it, **Then** the review's response-first-observed time is set to that later run's collection time (not the original review-first-observed time).
4. **Given** a stored review that already has a response and a recorded response-first-observed time, **When** a later collection run sees the same or an edited response, **Then** the response-first-observed time is unchanged.

### Edge Cases

- A business **edits** its reply between runs: the response text may be refreshed to the latest wording, but the response-first-observed time stays at the original first-observation moment (we observed *a* reply then; edits don't reset appearance).
- A response **disappears** (business deletes the reply, or a run fails to parse it): the stored response text and its first-observed time are retained; we do not clear either on absence. (Read-only collection; absence in one run is not treated as deletion.)
- The **same review is collected twice concurrently** (race): the review is inserted once; whichever path wins, a responded review ends up with a non-empty first-observed time and an unresponded one with an empty time. No duplicate reviews are created.
- Reviews collected **before this feature existed** have an empty response-first-observed time even if they carry a response, because we never actually recorded when we first saw that response. This absence is truthful and must not be back-filled with a fabricated time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record, per review, a response-first-observed time representing the collection run during which a business response was first seen on that review.
- **FR-002**: The response-first-observed time MUST be set exactly once, at the transition from "review has no stored response" to "review has a stored response," and MUST NOT change on any later collection run.
- **FR-003**: The response-first-observed time MUST remain empty for any review that has never had a stored response.
- **FR-004**: When a later run sees a response on a review that previously had none, the system MUST use that later run's collection time (not the review's own first-observed time) as the response-first-observed time.
- **FR-005**: Editing/refreshing the stored response text on a subsequent run MUST NOT alter the response-first-observed time.
- **FR-006**: The response-first-observed time MUST NOT influence review de-duplication: a review whose only change between runs is the appearance of a response MUST update in place, never be re-inserted as a new review.
- **FR-007**: The behavior MUST be identical for every review source that produces responses (Yandex Maps and 2GIS), with no source-specific special casing.
- **FR-008**: The response-first-observed time MUST be exposed on the review record returned by the reviews API.
- **FR-009**: Existing reviews stored before this feature MUST retain an empty response-first-observed time (no fabricated back-fill).

### Key Entities *(include if feature involves data)*

- **Review**: An existing collected review. Gains one new attribute — the **response first-observed time** — a nullable point in time. Empty until a response is first seen; set once at that moment; immutable thereafter. Sits alongside the review's existing review-first-observed time and its stored response text; does not participate in the review's de-duplication identity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of reviews collected with a response present record a non-empty response-first-observed time on the run that first stores that response.
- **SC-002**: 100% of reviews with no stored response have an empty response-first-observed time.
- **SC-003**: For a review re-collected across N runs after its response first appears, the response-first-observed time is identical across all N reads (0 drift).
- **SC-004**: Introducing the timestamp causes 0 additional review de-duplication changes — re-collecting an unchanged set of reviews (with or without responses) inserts 0 new duplicate reviews.
- **SC-005**: The response-first-observed time is populated correctly for both Yandex Maps and 2GIS collected reviews with 0 source-specific handling differences.

## Assumptions

- "First observed" is defined as the collection run's own time (the same time basis already used to stamp a review's first-observed time); sub-run precision is not required.
- Responses are already extracted and stored by the existing collection pipeline for both supported sources; this feature only adds the timestamp, not new parsing of response content.
- Absence of a response in a given run is not treated as a deletion; stored responses and their first-observed times are retained across runs (read-only collection).
- No user-facing web display is required in this feature; exposing the value on the reviews API is sufficient. Frontend presentation is a later, separate feature.
- No back-fill of historical reviews is performed; their empty response-first-observed time is the correct, truthful value.
