import hashlib
import re


def normalize_text(value: str | None, *, lowercase: bool = False) -> str:
    if value is None:
        return ""
    text = value.strip()
    text = re.sub(r"\s+", " ", text)
    if lowercase:
        text = text.lower()
    return text


def build_review_hash(
    author_name: str | None,
    rating: int,
    review_date_text: str | None,
    review_text: str,
) -> str:
    payload = "|".join(
        [
            normalize_text(author_name, lowercase=True),
            str(rating),
            normalize_text(review_date_text, lowercase=True),
            normalize_text(review_text, lowercase=False),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
