"""Response models for the network overview dashboard (feature 009).

Mirrors specs/009-network-overview/contracts/dashboard-overview.md. Nullable
delta / per-platform fields are None when history is absent or the metric cannot
be computed (rendered as "—" / "нет данных" by the frontend).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OverviewHeader(BaseModel):
    new_in_period: int
    unanswered_over_24h: int
    fresh_negatives_2h: int


class KpiHero(BaseModel):
    network_avg_rating: float | None
    network_avg_rating_delta: float | None
    new_in_period: int
    new_today: int
    # feature 014: period-over-period deltas (None when period has no predecessor)
    new_in_period_delta: int | None = None
    unanswered_delta_period: int | None = None
    period_days: int | None = None
    total_reviews: int
    avg_per_day: float
    unanswered_total: int
    unanswered_delta_24h: int
    overdue_24h: int


class KpiStrip(BaseModel):
    response_avg_min: int | None
    response_median_min: int | None
    response_p95_min: int | None
    response_approximate: bool
    sla_percent: float | None
    positivity_percent: float
    reputation_index: float | None
    # feature 014: period-over-period deltas (None when period has no predecessor)
    response_avg_min_delta: int | None = None
    sla_percent_delta: float | None = None
    positivity_percent_delta: float | None = None
    reputation_index_delta: float | None = None


class DistributionBar(BaseModel):
    star: int
    count: int
    percent: float


class RatingDistribution(BaseModel):
    bars: list[DistributionBar]
    share_4_5: float
    share_1_3: float
    total: int


class SentimentBlock(BaseModel):
    positive: int
    neutral: int
    negative: int
    positive_percent: float
    neutral_percent: float
    negative_percent: float
    analyzed_total: int


class PlatformCount(BaseModel):
    platform: str
    review_count: int


class PlatformCard(BaseModel):
    platform: str
    weighted_rating: float | None
    rating_delta: float | None
    negativity_percent: float | None
    response_speed_hours: float | None


class AttentionItem(BaseModel):
    type: str
    title: str
    subtitle: str
    value: float
    severity: str
    link: str
    rule_id: UUID | None = None
    rule_name: str | None = None


class WorstLocation(BaseModel):
    organization_id: str
    city: str | None
    name: str | None
    rating: float | None
    rating_delta: float | None
    unanswered_count: int


class AspectSentiment(BaseModel):
    pos: int
    neu: int
    neg: int


class TrendingAspect(BaseModel):
    category: str
    mentions: int
    change_percent: float | None
    sentiment: AspectSentiment


class DashboardOverview(BaseModel):
    period: str
    platform: str
    generated_at: datetime
    header: OverviewHeader
    kpi_hero: KpiHero
    kpi_strip: KpiStrip
    rating_distribution: RatingDistribution
    sentiment: SentimentBlock
    platform_breakdown: list[PlatformCount]
    platform_cards: list[PlatformCard]
    attention: list[AttentionItem]
    worst_locations: list[WorstLocation]
    trending_aspects: list[TrendingAspect]
