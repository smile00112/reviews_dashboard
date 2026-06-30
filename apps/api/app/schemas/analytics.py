from uuid import UUID

from pydantic import BaseModel


class TopProblemCategory(BaseModel):
    category: str
    description: str
    count: int


class OrganizationAnalyticsSummary(BaseModel):
    organization_id: UUID
    total_reviews: int
    analyzed_reviews: int
    sentiment_distribution: dict[str, int]
    sentiment_percent: dict[str, float]
    average_sentiment_score: float
    reviews_with_problems: int
    reviews_with_problems_percent: float
    top_problem_categories: list[TopProblemCategory]
    rating_sentiment_mismatch_count: int


class AnalyzeResult(BaseModel):
    organization_id: UUID
    analyzed: int
    skipped: int
