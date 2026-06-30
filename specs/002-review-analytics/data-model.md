# Data Model: Review Analytics

**Feature**: `002-review-analytics` | **Date**: 2026-06-30

Additive only. No existing column is altered or removed. Dedup hash inputs
(`author_name | rating | review_date_text | review_text`) are untouched.

## Modified: `reviews` (additive columns)

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `sentiment` | text | yes | null | `positive` \| `negative` \| `neutral`; null = not yet analyzed |
| `sentiment_score` | double precision | yes | null | bounded [-1.0, 1.0] |
| `sentiment_confidence` | double precision | yes | null | [0.0, 1.0] |
| `rating_sentiment_mismatch` | boolean | yes | null | true when rating≥4 & negative, or rating≤2 & positive |
| `problems` | jsonb | yes | null | list of Problem objects (see below); `[]` = analyzed, none found |
| `analyzed_at` | timestamptz | yes | null | when analysis last ran for this row |

`review_date` (existing, currently unused `Date` column) becomes populated by the new
date normalization in the parser path.

### Problem object (element of `problems` JSONB array)

```json
{
  "category": "качество_еды",
  "description": "Проблемы с качеством еды",
  "keywords_found": ["холодное", "невкусно"],
  "severity": "high",
  "context": "...еда холодная и невкусно совсем..."
}
```

- `category` ∈ {`качество_еды`, `обслуживание`, `чистота`, `цены`, `ожидание`, `атмосфера`, `технические`, `размер_порций`}
- `severity` ∈ {`low`, `medium`, `high`}

## Computed (not stored): OrganizationAnalyticsSummary

Returned by the analytics endpoint; derived on read from the org's analyzed reviews.

| Field | Type | Notes |
|-------|------|-------|
| `organization_id` | uuid | |
| `total_reviews` | int | reviews considered |
| `analyzed_reviews` | int | reviews with non-null `sentiment` |
| `sentiment_distribution` | object | `{positive, negative, neutral}` counts |
| `sentiment_percent` | object | same keys, percentages |
| `average_sentiment_score` | float | mean over analyzed reviews |
| `reviews_with_problems` | int | |
| `reviews_with_problems_percent` | float | |
| `top_problem_categories` | array | `[{category, description, count}]` ranked desc |
| `rating_sentiment_mismatch_count` | int | possible fake/sarcasm signal |

Empty org → all counts 0, distributions zeroed, HTTP 200.

## Invariants

- Analysis fields are derived; recomputation MUST be idempotent and MUST NOT change `content_hash`, raw `review_text`, `rating`, `author_name`, or `review_date_text`.
- `problems` null vs `[]`: null = never analyzed; `[]` = analyzed, no problems detected.
- Analytics MUST be computed locally; no field is sourced from an external service.
