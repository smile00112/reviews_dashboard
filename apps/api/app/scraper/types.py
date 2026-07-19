from dataclasses import dataclass, field
from datetime import date

# Runaway guard for uncapped ("collect everything") passes. Pagination already
# stops when a page yields no new reviews; at ~50 reviews/page this covers
# ~5000, well above the largest known org. Shared by the CLI (--all-reviews)
# and the reviews job's full passes (feature 011).
ALL_REVIEWS_MAX_PAGES = 100


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
    # True only when pagination was provably exhausted (end of the platform's
    # list reached before any limit/max_pages cap, with no skipped page).
    # Scroll-based Playwright scrapers never set it: default False = "coverage
    # unknown" and downstream removal marking stays disabled.
    full_pass: bool = False
    needs_manual_action: bool = False
    error_code: str | None = None
    error_message: str | None = None
    debug_screenshot: str | None = None
    debug_html: str | None = None
