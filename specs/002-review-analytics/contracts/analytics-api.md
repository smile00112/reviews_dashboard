# API Contract: Review Analytics

**Feature**: `002-review-analytics`

All endpoints internal (no auth), JSON, base path `/api`. Consistent with existing API.

## Reviews API — analysis fields (extends existing responses)

Existing review response objects (`GET /api/reviews`, `GET /api/organizations/{id}/reviews`)
gain additive, nullable fields:

```json
{
  "id": "…", "rating": 5, "review_text": "…", "review_date": "2026-05-02",
  "sentiment": "negative",
  "sentiment_score": -0.6,
  "sentiment_confidence": 0.4,
  "rating_sentiment_mismatch": true,
  "problems": [
    {"category": "ожидание", "description": "Проблемы с ожиданием",
     "keywords_found": ["долго ждать"], "severity": "medium", "context": "…"}
  ],
  "analyzed_at": "2026-06-30T10:00:00Z"
}
```

Null `sentiment`/`problems` = review not yet analyzed. No existing field changes type.

## POST /api/organizations/{id}/analyze

Run (or re-run) analysis over all stored reviews of the organization. Idempotent.

- **200** `{ "organization_id": "…", "analyzed": 42, "skipped": 0 }`
- **404** organization not found.
- Does NOT re-scrape, does NOT change any `content_hash`.

## GET /api/organizations/{id}/analytics

Per-organization analytics summary (computed on read).

**200**:

```json
{
  "organization_id": "…",
  "total_reviews": 120,
  "analyzed_reviews": 120,
  "sentiment_distribution": {"positive": 80, "negative": 30, "neutral": 10},
  "sentiment_percent": {"positive": 66.7, "negative": 25.0, "neutral": 8.3},
  "average_sentiment_score": 0.21,
  "reviews_with_problems": 28,
  "reviews_with_problems_percent": 23.3,
  "top_problem_categories": [
    {"category": "обслуживание", "description": "Проблемы с обслуживанием", "count": 14},
    {"category": "ожидание", "description": "Проблемы с ожиданием", "count": 9}
  ],
  "rating_sentiment_mismatch_count": 3
}
```

- **200** with zeroed fields when the organization has no reviews.
- **404** organization not found.

## Behavior guarantees

- Analytics deterministic & local (Constitution VI); no external calls.
- Analysis safe-degrades: malformed/empty text → `sentiment=neutral`, `problems=[]`, no error.
- Re-running `/analyze` leaves every review's `content_hash` unchanged (dedup contract).
