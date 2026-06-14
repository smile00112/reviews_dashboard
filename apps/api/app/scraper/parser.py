import re
from datetime import date

from app.scraper.types import ParsedOrganization, ParsedReview


def parse_rating(text: str) -> int | None:
    match = re.search(r"(\d)", text)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 5:
            return value
    return None


def parse_reviews_from_html(html: str) -> tuple[ParsedOrganization, list[ParsedReview]]:
    """Best-effort parser for Yandex Maps review blocks in page HTML."""
    org = ParsedOrganization()
    reviews: list[ParsedReview] = []

    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
    if title_match:
        org.name = title_match.group(1).strip()

    rating_match = re.search(r'business-rating-badge-view__rating[^>]*>([\d.,]+)', html)
    if rating_match:
        try:
            org.rating = float(rating_match.group(1).replace(",", "."))
        except ValueError:
            pass

    count_match = re.search(r"(\d+)\s+отзыв", html, re.IGNORECASE)
    if count_match:
        org.review_count = int(count_match.group(1))

    review_blocks = re.findall(
        r'business-review-view__body[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if not review_blocks:
        review_blocks = re.findall(
            r'class="[^"]*review[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

    for block in review_blocks[:200]:
        author_match = re.search(r'business-review-view__author[^>]*>([^<]+)', block, re.IGNORECASE)
        text_match = re.search(r'business-review-view__body-text[^>]*>([^<]+)', block, re.IGNORECASE)
        date_match = re.search(r'business-review-view__date[^>]*>([^<]+)', block, re.IGNORECASE)
        stars = len(re.findall(r'business-rating-badge-view__star[^>]*_full', block, re.IGNORECASE))
        if stars == 0:
            stars = parse_rating(block) or 0
        body = text_match.group(1).strip() if text_match else ""
        if not body or stars < 1:
            continue
        reviews.append(
            ParsedReview(
                author_name=author_match.group(1).strip() if author_match else None,
                rating=stars,
                review_text=body,
                review_date_text=date_match.group(1).strip() if date_match else None,
            )
        )

    return org, reviews
