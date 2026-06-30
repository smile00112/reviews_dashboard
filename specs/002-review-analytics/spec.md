# Feature Specification: Review Analytics & Structured Parsing

**Feature Branch**: `002-review-analytics`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "Rule-based review analytics (sentiment, problem categorization, rating-sentiment mismatch) plus structured BeautifulSoup parsing with date normalization and guest-review filtering, ported from BrandTrackerAI parser"

## Context

Ported, in part, from the sibling `BrandTrackerAI_Parser` project. Only the deterministic,
local pieces are in scope here — sentiment, problem extraction, date normalization,
structured parsing, and guest-review filtering. Multi-provider (2GIS), schedulers, and
CSV output are explicitly NOT ported (out of scope per constitution).

Authorized by constitution v1.1.0, Principle VI (Deterministic Local Analytics): all
analytics MUST be computed locally from rule-based dictionaries/regex, MUST NOT call any
LLM/external service, MUST degrade safely on bad input, and MUST NOT mutate raw review
data or dedup hash inputs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sentiment & problem insight on reviews (Priority: P1)

An operator viewing collected reviews wants each review tagged with a sentiment
(positive / negative / neutral) and, when negative signals are present, a set of problem
categories (food quality, service, cleanliness, price, waiting time, atmosphere,
technical, portion size). This turns a flat list of text into scannable, filterable signal.

**Why this priority**: This is the core value of the feature — deriving insight from text
the system already collects, with no new infrastructure. Everything else supports it.

**Independent Test**: Feed a set of known review texts through the analysis service and
assert the expected sentiment label and problem categories per text; verify a stored
review exposes `sentiment` and `problems` via the API.

**Acceptance Scenarios**:

1. **Given** a review "Очень вкусно, отличное обслуживание", **When** analyzed, **Then** sentiment is `positive` with score > 0.
2. **Given** a review "Ужасно долго ждали, еда холодная", **When** analyzed, **Then** sentiment is `negative` and problems include `ожидание` and `качество_еды`.
3. **Given** an empty or whitespace-only review text, **When** analyzed, **Then** sentiment is `neutral`, problems are empty, and no error is raised.
4. **Given** an analyzed review, **When** fetched via the reviews API, **Then** the response includes its `sentiment`, `sentiment_score`, and `problems`.

---

### User Story 2 - Aggregate analytics per organization (Priority: P2)

An operator wants a per-organization summary: sentiment distribution (counts/percent),
top recurring problem categories, share of reviews with problems, and count of
rating↔sentiment mismatches (e.g. 4–5★ with strongly negative text — possible fake or
sarcasm). This shows trends, not just per-review tags.

**Why this priority**: Aggregation is where operators get actionable direction ("service
complaints up this month"). Depends on P1 per-review analysis existing.

**Independent Test**: Seed N analyzed reviews for one organization, call the analytics
summary endpoint, assert distribution counts, top problems, and mismatch count match
hand-computed values.

**Acceptance Scenarios**:

1. **Given** 10 analyzed reviews for an org (6 positive, 3 negative, 1 neutral), **When** the summary is requested, **Then** it reports those counts and correct percentages.
2. **Given** reviews with problems in multiple categories, **When** the summary is requested, **Then** top problem categories are ranked by frequency.
3. **Given** a 5★ review whose text is strongly negative, **When** the summary is requested, **Then** it is counted as a rating↔sentiment mismatch.

---

### User Story 3 - Robust structured parsing with normalized dates (Priority: P3)

The scraper should parse review blocks with a structured HTML parser (BeautifulSoup)
instead of brittle regex, normalize relative/textual dates ("вчера", "5 дней назад",
"2 мая 2024", "DD.MM.YYYY") into `YYYY-MM-DD`, and exclude business/owner responses from
the guest-review set (responses remain stored as `response_text`, not as standalone
reviews).

**Why this priority**: Improves data quality feeding P1/P2, but the analytics layer can
ship against existing parsed data first; parsing hardening is independent and lower-risk
to sequence last.

**Independent Test**: Run the parser against saved Yandex review-page HTML fixtures and
assert extracted author/rating/date plus a populated `review_date` (date), and that
owner-response blocks are not emitted as guest reviews.

**Acceptance Scenarios**:

1. **Given** a review block with date text "5 дней назад", **When** parsed, **Then** `review_date` is set to the date 5 days before the scrape date.
2. **Given** a review block with rating expressed via `aria-label="Оценка 4 Из 5"`, **When** parsed, **Then** rating is 4.
3. **Given** an HTML block that is an owner response ("Спасибо за отзыв! ..."), **When** parsed, **Then** it is not returned as a guest review.
4. **Given** unparseable date text, **When** parsed, **Then** `review_date` is null and `review_date_text` is preserved (no crash).

---

### Edge Cases

- Review text in mixed languages or with no dictionary hits → sentiment `neutral`, empty problems.
- Negation ("не вкусно") MUST be treated as negative, not positive (dictionary contains negative multi-word forms).
- Re-analysis of an already-analyzed review MUST be idempotent and MUST NOT change the dedup `content_hash`.
- Analytics summary for an organization with zero reviews → empty/zeroed summary, HTTP 200, not an error.
- Date normalization MUST NOT raise on garbage input; it returns null date and keeps the original text.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST classify each review's text as `positive`, `negative`, or `neutral` using a local rule-based dictionary, returning a bounded score in [-1.0, 1.0] and a confidence value.
- **FR-002**: System MUST extract zero or more problem categories per review from a fixed taxonomy (food quality, service, cleanliness, price, waiting, atmosphere, technical, portion size), each with matched keywords and an estimated severity (low/medium/high).
- **FR-003**: System MUST flag a review as a rating↔sentiment mismatch when rating ≥ 4 with negative sentiment, or rating ≤ 2 with positive sentiment.
- **FR-004**: System MUST persist per-review analysis results (sentiment label, score, confidence, problems, mismatch flag) associated with the review without altering raw review fields or the dedup `content_hash`.
- **FR-005**: System MUST expose per-review analysis through the existing reviews API responses.
- **FR-006**: System MUST provide a per-organization analytics summary: sentiment distribution (counts + percent), average sentiment score, reviews-with-problems count/percent, ranked top problem categories, and rating↔sentiment mismatch count.
- **FR-007**: Analytics MUST be deterministic and computed locally; the system MUST NOT call any LLM, hosted ML, or external inference service (Constitution Principle VI).
- **FR-008**: Analysis functions MUST degrade safely — empty/None/malformed text yields a neutral/empty result and MUST NOT raise.
- **FR-009**: Scraper MUST parse review blocks using a structured HTML parser (BeautifulSoup), extracting author, rating (via star count or `aria-label`), date text, and body.
- **FR-010**: System MUST normalize review date text (relative forms, Russian/English month names, `DD.MM.YYYY`) into a `YYYY-MM-DD` date; unparseable input yields a null date while preserving the original `review_date_text`.
- **FR-011**: Parser MUST exclude owner/business responses from the guest-review set while preserving the existing `response_text` storage behavior.
- **FR-012**: Analysis MUST be (re-)runnable over already-stored reviews (e.g., a backfill/trigger path), not only at scrape time, and MUST be idempotent.

### Key Entities *(include if feature involves data)*

- **ReviewAnalysis**: Derived analysis for a single review — sentiment label, sentiment score, confidence, list of problems (category, keywords, severity, context snippet), rating↔sentiment mismatch flag. One-to-one with a Review; never feeds the dedup hash.
- **Problem**: A detected complaint within a review — category (from fixed taxonomy), matched keywords, severity, short context.
- **OrganizationAnalyticsSummary**: Aggregate over an organization's analyzed reviews — sentiment distribution, average score, problems-by-category ranking, problem coverage percent, mismatch count. Computed (not necessarily stored).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of stored reviews with non-empty text receive a sentiment label after analysis runs.
- **SC-002**: On a labeled fixture set of ≥ 30 Russian reviews, sentiment classification agrees with the hand label for ≥ 80% of clearly positive/negative cases.
- **SC-003**: Date normalization converts ≥ 95% of the supported date-text patterns in the fixture set to a valid `YYYY-MM-DD` date.
- **SC-004**: An operator can retrieve an organization analytics summary and see top problem categories and mismatch count in a single API call.
- **SC-005**: Analysis never raises on the edge-case fixture set (empty, garbage, mixed-language, owner-response text) — 0 unhandled exceptions.
- **SC-006**: Re-running analysis over the same reviews does not change any review's `content_hash` (dedup contract preserved).

## Assumptions

- Reviews are predominantly Russian-language; dictionaries target Russian with partial English month support.
- Rule-based dictionary accuracy is "good enough for triage", not ML-grade; precision/recall tuning is acceptable iteratively.
- Per-review analysis is stored to avoid recomputation; the org summary may be computed on read for the expected scale (tens of orgs, low thousands of reviews).
- Existing `Review` model and dedup hash inputs (`author_name | rating | review_date_text | review_text`) remain unchanged; analysis fields are additive.
- Structured-parsing change targets the same Yandex review block markup the current regex parser handles; HTML fixtures are captured for tests.
- No application auth is added (consistent with MVP); analytics endpoints are internal like the rest of the API.
