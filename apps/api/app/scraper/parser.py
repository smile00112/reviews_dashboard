"""Structured (BeautifulSoup) parser for Yandex Maps review-page HTML.

Replaces the previous regex parser. Extracts organization metadata and guest
reviews, normalizes review dates, and excludes owner/business responses from the
guest-review set (responses are still attached as ``response_text`` when adjacent).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from app.scraper.normalize import normalize_review_date
from app.scraper.types import ParsedOrganization, ParsedReview

# Phrases that mark a block as a business/owner response rather than a guest review.
OWNER_RESPONSE_MARKERS: tuple[str, ...] = (
    "спасибо за отзыв",
    "благодарим за отзыв",
    "благодарим вас за",
    "приносим извинения",
    "приносим свои извинения",
    "администрация",
    "ваш отзыв очень важен",
    "команда заведения",
    "официальный ответ",
)

_MAX_REVIEWS = 200


def _text(node: Tag | None) -> str:
    return node.get_text(strip=True) if node else ""


def is_owner_response(text: str) -> bool:
    """True if the text reads as a business reply, not a customer review."""
    lowered = text.lower()
    return any(marker in lowered for marker in OWNER_RESPONSE_MARKERS)


def _parse_rating(block: Tag) -> int:
    # Prefer the explicit aria-label, e.g. "Оценка 4 Из 5".
    for stars in block.select(".business-rating-badge-view__stars"):
        label = stars.get("aria-label") or ""
        m = re.search(r"Оценка\s+(\d+)\s+Из\s+5", label, re.IGNORECASE)
        if m:
            value = int(m.group(1))
            if 1 <= value <= 5:
                return value
        full = stars.select(".business-rating-badge-view__star._full")
        if full:
            return len(full)
    # Fallback: count any "_full" star markers in the block.
    full = block.select(".business-rating-badge-view__star._full")
    return len(full) if full else 0


def parse_reviews_from_html(html: str) -> tuple[ParsedOrganization, list[ParsedReview]]:
    soup = BeautifulSoup(html or "", "html.parser")
    org = ParsedOrganization()

    h1 = soup.find("h1")
    if h1:
        org.name = _text(h1)

    rating_badge = soup.select_one(".business-rating-badge-view__rating")
    if rating_badge:
        try:
            org.rating = float(_text(rating_badge).replace(",", "."))
        except ValueError:
            pass

    count_match = re.search(r"(\d+)\s+отзыв", soup.get_text(" "), re.IGNORECASE)
    if count_match:
        org.review_count = int(count_match.group(1))

    reviews: list[ParsedReview] = []
    for block in soup.select(".business-review-view")[:_MAX_REVIEWS]:
        # Yandex renamed __body-text → __body / spoiler-view__text; itemprop is most stable.
        body = (
            _text(block.select_one("[itemprop='reviewBody']"))
            or _text(block.select_one(".business-review-view__body"))
            or _text(block.select_one(".business-review-view__body-text"))
        )
        if not body:
            continue
        # Skip blocks that are themselves owner responses.
        if is_owner_response(body):
            continue

        rating = _parse_rating(block)
        if rating < 1:
            continue

        author = _text(block.select_one(".business-review-view__author-name")) or (
            _text(block.select_one(".business-review-view__author")) or None
        )
        date_text = _text(block.select_one(".business-review-view__date")) or None

        # An owner response nested within the review block, if present.
        response_node = (
            block.select_one(".business-review-comment-content__bubble")
            or block.select_one(".business-review-view__comment .spoiler-view__text")
        )
        response_text = _text(response_node) or None

        reviews.append(
            ParsedReview(
                author_name=author,
                rating=rating,
                review_text=body,
                review_date_text=date_text,
                review_date=normalize_review_date(date_text),
                response_text=response_text,
            )
        )

    return org, reviews
