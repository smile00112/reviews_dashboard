from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.analysis.analyzer import ReviewAnalyzer, summarize
from app.models.organization import Organization
from app.models.review import Review


class AnalysisService:
    """Apply deterministic local analytics to stored reviews and aggregate them.

    Never mutates raw review fields (text, rating, author, date text) or the dedup
    ``content_hash`` — only the additive analysis columns.
    """

    def __init__(self, db: Session):
        self.db = db
        self._analyzer = ReviewAnalyzer()

    def analyze_review(self, review: Review, *, now: datetime | None = None) -> None:
        """Compute and assign analysis fields on a Review (no commit)."""
        result = self._analyzer.analyze(review.review_text, review.rating)
        review.sentiment = result["sentiment"]
        review.sentiment_score = result["sentiment_score"]
        review.sentiment_confidence = result["sentiment_confidence"]
        review.rating_sentiment_mismatch = result["rating_sentiment_mismatch"]
        review.problems = result["problems"]
        review.analyzed_at = now or datetime.now(timezone.utc)

    def analyze_organization(self, organization_id: UUID) -> dict | None:
        """Backfill analysis over all of an organization's reviews. Idempotent.

        Returns None if the organization does not exist.
        """
        org = self.db.get(Organization, organization_id)
        if org is None:
            return None

        reviews = self.db.query(Review).filter(Review.organization_id == organization_id).all()
        now = datetime.now(timezone.utc)
        for review in reviews:
            self.analyze_review(review, now=now)
        self.db.commit()
        return {"organization_id": str(organization_id), "analyzed": len(reviews), "skipped": 0}

    def summary(self, organization_id: UUID) -> dict | None:
        """Per-organization analytics summary, computed on read.

        Returns None if the organization does not exist; a zeroed summary if it has
        no reviews.
        """
        org = self.db.get(Organization, organization_id)
        if org is None:
            return None

        reviews = self.db.query(Review).filter(Review.organization_id == organization_id).all()
        rows = [
            {
                "sentiment": r.sentiment,
                "sentiment_score": r.sentiment_score,
                "problems": r.problems,
                "rating_sentiment_mismatch": r.rating_sentiment_mismatch,
            }
            for r in reviews
        ]
        return {"organization_id": str(organization_id), **summarize(rows)}
