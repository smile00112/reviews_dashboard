import hashlib
import re
from datetime import date, datetime, timedelta, timezone

# Russian + English month names → month number.
_MONTHS: dict[str, int] = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def normalize_review_date(text: str | None, *, today: date | None = None) -> date | None:
    """Best-effort conversion of Yandex review date text into a ``date``.

    Handles ISO (``YYYY-MM-DD``), ``DD.MM.YYYY``, full/partial Russian & English
    month names, and relative forms (сегодня/вчера/позавчера, "N дней/недель/месяцев/
    лет назад"). Returns ``None`` for empty or unrecognised input — never raises.
    """
    if not text or not isinstance(text, str):
        return None

    today = today or datetime.now(timezone.utc).date()
    raw = text.strip()
    lowered = raw.lower()

    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw)

        dot = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw)
        if dot:
            d, m, y = (int(g) for g in dot.groups())
            return date(y, m, d)

        if "позавчера" in lowered:
            return today - timedelta(days=2)
        if "вчера" in lowered:
            return today - timedelta(days=1)
        if "сегодня" in lowered:
            return today

        ago = re.search(r"(\d+)\s+(день|дня|дней|недел|месяц|год|года|лет)\w*\s+назад", lowered)
        if ago:
            n = int(ago.group(1))
            unit = ago.group(2)
            if unit.startswith("недел"):
                return today - timedelta(weeks=n)
            if unit.startswith("месяц"):
                return today - timedelta(days=n * 30)
            if unit in ("год", "года", "лет"):
                return today - timedelta(days=n * 365)
            return today - timedelta(days=n)  # день/дня/дней

        full = re.search(r"(\d{1,2})\s+([а-яёa-z]+)\s+(\d{4})", lowered)
        if full and full.group(2) in _MONTHS:
            return date(int(full.group(3)), _MONTHS[full.group(2)], int(full.group(1)))

        partial = re.search(r"(\d{1,2})\s+([а-яёa-z]+)", lowered)
        if partial and partial.group(2) in _MONTHS:
            return date(today.year, _MONTHS[partial.group(2)], int(partial.group(1)))
    except (ValueError, OverflowError):
        return None

    return None


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
