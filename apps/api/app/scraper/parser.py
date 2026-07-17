"""Structured (BeautifulSoup) parser for Yandex Maps review-page HTML.

Replaces the previous regex parser. Extracts organization metadata and guest
reviews, normalizes review dates, and excludes owner/business responses from the
guest-review set (responses are still attached as ``response_text`` when adjacent).
"""

from __future__ import annotations

import json
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


def _microdata_number(scope: Tag, itemprop: str, *, as_int: bool) -> float | int | None:
    """Read a schema.org itemprop value (``content`` attr preferred over text) and
    coerce to a number. Returns None when absent or unparseable."""
    el = scope.select_one(f"[itemprop='{itemprop}']")
    if el is None:
        return None
    raw = (el.get("content") or _text(el) or "").strip().replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", raw)
    if not match:
        return None
    return int(float(match.group())) if as_int else float(match.group())


def is_owner_response(text: str) -> bool:
    """True if the text reads as a business reply, not a customer review."""
    lowered = text.lower()
    return any(marker in lowered for marker in OWNER_RESPONSE_MARKERS)


def _normalize_match_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _business_comments_from_state(soup: BeautifulSoup) -> list[dict]:
    """Business replies from the embedded SPA state JSON.

    On live pages the org reply is collapsed behind "Посмотреть ответ
    организации" — the reply text is NOT in the review DOM at all. It only
    exists in the ``<script class="state-view">`` JSON under
    ``reviewResults.reviews[].businessComment``. Returns a list of
    ``{author, text, comment}`` dicts (normalized author/text for matching).
    Malformed or absent state JSON yields ``[]`` — never raises.
    """
    entries: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/json"}):
        content = script.string or ""
        if '"reviewResults"' not in content:
            continue
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            continue
        results = _find_nested_key(data, "reviewResults")
        if not isinstance(results, dict):
            continue
        for item in results.get("reviews") or []:
            if not isinstance(item, dict):
                continue
            comment = item.get("businessComment")
            comment_text = comment.get("text") if isinstance(comment, dict) else None
            if not comment_text:
                continue
            author = item.get("author")
            entries.append(
                {
                    "author": _normalize_match_text(author.get("name") if isinstance(author, dict) else None),
                    "text": _normalize_match_text(item.get("text")),
                    "comment": comment_text.strip(),
                }
            )
    return entries


def _find_business_address(obj: object, depth: int = 0) -> str | None:
    """Depth-first search for the page's own business-search-item entry
    (``{"type": "business", "address": "...", ...}``) in the embedded state
    JSON. Present on both the org overview and reviews-tab pages, unlike the
    ``itemprop='address'`` meta tag which only renders on the overview page."""
    if depth > 12:
        return None
    if isinstance(obj, dict):
        address = obj.get("address")
        if obj.get("type") == "business" and isinstance(address, str) and address.strip():
            return address.strip()
        for value in obj.values():
            found = _find_business_address(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_business_address(value, depth + 1)
            if found:
                return found
    return None


def _address_from_state(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", attrs={"type": "application/json"}):
        content = script.string or ""
        if '"address"' not in content:
            continue
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            continue
        found = _find_business_address(data)
        if found:
            return found
    return None


def _address_from_meta(soup: BeautifulSoup) -> str | None:
    el = soup.select_one("meta[itemprop='address']")
    content = (el.get("content") if el else None) or ""
    return content.strip() or None


def _find_nested_key(obj, key: str, depth: int = 0):
    """Depth-first search for ``key`` in nested dicts/lists (state JSON layout
    shifts between page versions, so the path is not hardcoded)."""
    if depth > 8:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find_nested_key(value, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_nested_key(value, key, depth + 1)
            if found is not None:
                return found
    return None


def _match_state_comment(entries: list[dict], author: str | None, body: str) -> str | None:
    """Pick the reply for a DOM review: author must match; among an author's
    entries the review texts must agree (prefix match — the DOM body may be a
    truncated version of the full JSON text, or vice versa)."""
    norm_author = _normalize_match_text(author)
    norm_body = _normalize_match_text(body).rstrip("…").rstrip(".")
    candidates = [e for e in entries if e["author"] == norm_author]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["comment"]
    for entry in candidates:
        text = entry["text"].rstrip("…").rstrip(".")
        if text.startswith(norm_body) or norm_body.startswith(text):
            return entry["comment"]
    return None


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

    # Prefer schema.org aggregateRating microdata — stable across Yandex markup
    # churn — then fall back to the legacy badge selector / text scan (older pages
    # and test fixtures). ratingCount = оценки, reviewCount = отзывы.
    agg = soup.select_one("[itemprop='aggregateRating']") or soup

    org.rating = _microdata_number(agg, "ratingValue", as_int=False)
    if org.rating is None:
        rating_badge = soup.select_one(".business-rating-badge-view__rating")
        if rating_badge:
            try:
                org.rating = float(_text(rating_badge).replace(",", "."))
            except ValueError:
                pass

    org.review_count = _microdata_number(agg, "reviewCount", as_int=True)
    if org.review_count is None:
        count_match = re.search(r"(\d+)\s+отзыв", soup.get_text(" "), re.IGNORECASE)
        if count_match:
            org.review_count = int(count_match.group(1))

    org.rating_count = _microdata_number(agg, "ratingCount", as_int=True)

    org.address = _address_from_state(soup) or _address_from_meta(soup)

    state_comments = _business_comments_from_state(soup)

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
        # Live pages keep the reply collapsed ("Посмотреть ответ организации"):
        # no bubble node exists, so fall back to the state-view JSON.
        if response_text is None and state_comments:
            response_text = _match_state_comment(state_comments, author, body)

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
