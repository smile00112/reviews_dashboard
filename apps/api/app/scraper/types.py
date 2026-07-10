from dataclasses import dataclass, field
from datetime import date


@dataclass
class ParsedReview:
    author_name: str | None
    rating: int
    review_text: str
    review_date_text: str | None = None
    review_date: date | None = None
    response_text: str | None = None
    external_review_id: str | None = None


@dataclass
class ParsedOrganization:
    name: str | None = None
    rating: float | None = None
    review_count: int | None = None
    rating_count: int | None = None
    address: str | None = None


@dataclass
class ScrapeResult:
    organization: ParsedOrganization = field(default_factory=ParsedOrganization)
    reviews: list[ParsedReview] = field(default_factory=list)
    needs_manual_action: bool = False
    error_code: str | None = None
    error_message: str | None = None
    debug_screenshot: str | None = None
    debug_html: str | None = None
