"""Сбор метрик организации (рейтинг, число отзывов, число оценок).

Логика жила в scripts/scrape_metrics.py; вынесена в сервис, чтобы фоновая
задача и CLI использовали одну реализацию. Отдельные отзывы не читаются —
скраперы вызываются с metrics_only=True.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.enums import OrganizationScrapeStatus
from app.models.organization import Organization
from app.scraper.twogis_api import TwogisApiScraper
from app.scraper.types import ScrapeResult
from app.scraper.yandex_http import YandexHttpScraper
from app.scraper.yandex_scrapeops import YandexScrapeOpsScraper

# платформа -> (url, rating, review_count, rating_count, status, success-ts)
PLATFORM_COLUMNS: dict[str, tuple[str, str, str, str, str, str]] = {
    "yandex": (
        "yandex_url", "rating", "review_count", "yandex_rating_count",
        "yandex_scrape_status", "yandex_last_successful_scrape_at",
    ),
    "2gis": (
        "gis2_url", "gis2_rating", "gis2_review_count", "gis2_rating_count",
        "gis2_scrape_status", "gis2_last_successful_scrape_at",
    ),
}


class MetricsOutcome(str, enum.Enum):
    updated = "updated"
    failed = "failed"
    manual_action = "manual_action"


@dataclass
class MetricsResult:
    outcome: MetricsOutcome
    payload: dict = field(default_factory=dict)
    error_code: str | None = None


class Scrapers:
    """Лениво создаваемые скраперы, переиспользуемые в пределах прогона."""

    def __init__(self) -> None:
        self.yandex_http = YandexHttpScraper()
        self.yandex_proxy = YandexScrapeOpsScraper()
        self.twogis = TwogisApiScraper()

    def scrape(self, platform: str, url: str) -> ScrapeResult:
        if platform == "2gis":
            return self.twogis.scrape(url, metrics_only=True)
        # yandex: сначала browserless, затем ScrapeOps как фолбэк — на вызов
        # оператора, ошибку или пустой рейтинг.
        result = self.yandex_http.scrape(url, metrics_only=True)
        if result.needs_manual_action or result.error_code or result.organization.rating is None:
            fallback = self.yandex_proxy.scrape(url)
            if not (fallback.needs_manual_action or fallback.error_code) and fallback.organization.rating is not None:
                return fallback
        return result


def _as_float(value) -> float | None:
    return None if value is None else float(value)


class MetricsService:
    def __init__(self, db: Session, scrapers: Scrapers | None = None):
        self.db = db
        self.scrapers = scrapers or Scrapers()

    def refresh_organization(self, org: Organization, platform: str) -> MetricsResult:
        """Обновить метрики организации для одной площадки.

        Никогда не затирает известное значение пустым: скрап без рейтинга —
        это провал, а не повод обнулить цифру. Не коммитит: транзакцией
        управляет вызывающий.
        """
        url_col, rating_col, count_col, rating_count_col, status_col, ts_col = PLATFORM_COLUMNS[platform]
        url = getattr(org, url_col)
        payload = {
            "rating_before": _as_float(getattr(org, rating_col)),
            "review_count_before": getattr(org, count_col),
            "rating_count_before": getattr(org, rating_count_col),
        }

        result = self.scrapers.scrape(platform, url)

        if result.needs_manual_action:
            setattr(org, status_col, OrganizationScrapeStatus.needs_manual_action)
            return MetricsResult(MetricsOutcome.manual_action, payload, result.error_code)

        if result.error_code or result.organization.rating is None:
            setattr(org, status_col, OrganizationScrapeStatus.failed)
            return MetricsResult(MetricsOutcome.failed, payload, result.error_code or "no_rating")

        setattr(org, rating_col, result.organization.rating)
        if result.organization.review_count is not None:
            setattr(org, count_col, result.organization.review_count)
        if result.organization.rating_count is not None:
            setattr(org, rating_count_col, result.organization.rating_count)
        setattr(org, status_col, OrganizationScrapeStatus.success)
        setattr(org, ts_col, datetime.now(timezone.utc))

        payload.update(
            {
                "rating_after": _as_float(getattr(org, rating_col)),
                "review_count_after": getattr(org, count_col),
                "rating_count_after": getattr(org, rating_count_col),
            }
        )
        return MetricsResult(MetricsOutcome.updated, payload)
