"""Combine sentiment + problem extraction into a single review analysis, and
aggregate per-review results into an organization-level summary.

Deterministic and local (constitution Principle VI). Pure functions over plain
dicts/lists — no DB, no I/O, no external calls.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, TypedDict

from app.analysis.problems import Problem, ProblemExtractor
from app.analysis.sentiment import SentimentAnalyzer


class ReviewAnalysis(TypedDict):
    sentiment: str
    sentiment_score: float
    sentiment_confidence: float
    problems: list[Problem]
    rating_sentiment_mismatch: bool


class ReviewAnalyzer:
    def __init__(self) -> None:
        self._sentiment = SentimentAnalyzer()
        self._problems = ProblemExtractor()

    def analyze(self, text: str | None, rating: int | None = None) -> ReviewAnalysis:
        sentiment = self._sentiment.analyze(text)
        problems = self._problems.extract(text)
        return {
            "sentiment": sentiment["sentiment"],
            "sentiment_score": sentiment["score"],
            "sentiment_confidence": sentiment["confidence"],
            "problems": problems,
            "rating_sentiment_mismatch": self._is_mismatch(rating, sentiment["sentiment"]),
        }

    @staticmethod
    def _is_mismatch(rating: int | None, sentiment: str) -> bool:
        if rating is None:
            return False
        if rating >= 4 and sentiment == "negative":
            return True
        if rating <= 2 and sentiment == "positive":
            return True
        return False


class AnalyzedReview(TypedDict):
    """Minimal shape needed for aggregation (mapped from stored rows)."""

    sentiment: str | None
    sentiment_score: float | None
    problems: list[Problem] | None
    rating_sentiment_mismatch: bool | None


def summarize(reviews: Iterable[AnalyzedReview]) -> dict:
    """Aggregate analyzed reviews into an organization-level summary.

    Counts only reviews that have been analyzed (non-null ``sentiment``).
    Returns zeroed fields for an empty / fully-unanalyzed input.
    """
    rows = list(reviews)
    total = len(rows)
    analyzed = [r for r in rows if r.get("sentiment")]
    n = len(analyzed)

    distribution = {"positive": 0, "negative": 0, "neutral": 0}
    score_sum = 0.0
    with_problems = 0
    mismatch = 0
    category_counter: Counter[str] = Counter()

    for r in analyzed:
        sentiment = r.get("sentiment")
        if sentiment in distribution:
            distribution[sentiment] += 1
        score_sum += r.get("sentiment_score") or 0.0
        if r.get("rating_sentiment_mismatch"):
            mismatch += 1
        problems = r.get("problems") or []
        if problems:
            with_problems += 1
            category_counter.update(p["category"] for p in problems)

    def pct(part: int) -> float:
        return round(part / n * 100, 1) if n else 0.0

    from app.analysis.problems import PROBLEM_CATEGORIES

    top_problems = [
        {
            "category": cat,
            "description": PROBLEM_CATEGORIES.get(cat, {}).get("description", cat),
            "count": count,
        }
        for cat, count in category_counter.most_common(10)
    ]

    return {
        "total_reviews": total,
        "analyzed_reviews": n,
        "sentiment_distribution": distribution,
        "sentiment_percent": {k: pct(v) for k, v in distribution.items()},
        "average_sentiment_score": round(score_sum / n, 3) if n else 0.0,
        "reviews_with_problems": with_problems,
        "reviews_with_problems_percent": pct(with_problems),
        "top_problem_categories": top_problems,
        "rating_sentiment_mismatch_count": mismatch,
    }
