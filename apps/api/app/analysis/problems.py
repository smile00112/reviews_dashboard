"""Rule-based problem / complaint extraction from Russian review text.

Deterministic and local (constitution Principle VI). Degrades safely: empty / None /
non-string input yields an empty list and never raises.
"""

from __future__ import annotations

import re
from typing import TypedDict

# Fixed taxonomy: category -> (human description, keyword list).
PROBLEM_CATEGORIES: dict[str, dict[str, object]] = {
    "качество_еды": {
        "description": "Проблемы с качеством еды",
        "keywords": [
            "невкусно", "невкусный", "невкусная", "невкусное",
            "пересолено", "пересоленный", "недосолено",
            "пережарено", "пережаренный", "недожарено",
            "холодное", "холодный", "холодная",
            "испорчено", "испорченный", "просрочено", "просроченный",
            "не свежее", "не свежий", "не свежая",
            "плохое качество", "некачественный", "некачественная",
        ],
    },
    "обслуживание": {
        "description": "Проблемы с обслуживанием",
        "keywords": [
            "медленное обслуживание", "грубо", "грубый", "грубая",
            "невежливо", "невежливый", "неприветливо", "неприветливый",
            "игнорируют", "игнорирует", "не обращают внимания",
            "не помогли", "не обслужили", "плохое обслуживание",
            "некомпетентный", "некомпетентная", "ошибка в заказе",
            "неправильный заказ",
        ],
    },
    "чистота": {
        "description": "Проблемы с чистотой",
        "keywords": [
            "грязно", "грязный", "грязная", "грязное",
            "мусор", "крошки", "пятна", "не убрано",
            "грязная посуда", "грязные столы", "антисанитария",
            "неприятный запах", "воняет", "вонь",
        ],
    },
    "цены": {
        "description": "Проблемы с ценами",
        "keywords": [
            "дорого", "дорогой", "дорогая", "дорогое",
            "завышенные цены", "неоправданно дорого",
            "переплатил", "переплатили", "не стоит денег",
            "завысили цену", "завысили цены", "неадекватные цены",
        ],
    },
    "ожидание": {
        "description": "Проблемы с ожиданием",
        "keywords": [
            "долго ждать", "долгое ожидание", "очень долго", "слишком долго",
            "ждали час", "ждали полчаса", "не принесли",
            "забыли заказ", "потеряли заказ", "не привезли вовремя",
            "опоздали", "задержка", "долго готовят",
        ],
    },
    "атмосфера": {
        "description": "Проблемы с атмосферой",
        "keywords": [
            "шумно", "шумный", "громкая музыка", "тесно", "тесный",
            "душно", "душный", "неуютно", "плохая атмосфера",
            "неприятная обстановка",
        ],
    },
    "технические": {
        "description": "Технические проблемы",
        "keywords": [
            "не работает", "сломалось", "сломался",
            "не работает wi-fi", "не работает wifi", "не принимают карту",
            "не работает терминал", "проблемы с оплатой",
            "не работает приложение", "технические проблемы", "сбой",
        ],
    },
    "размер_порций": {
        "description": "Проблемы с размером порций",
        "keywords": [
            "маленькие порции", "маленькая порция", "не наелся", "не наелась",
            "не хватило", "скудные порции", "мало еды",
        ],
    },
}

SEVERE_WORDS: frozenset[str] = frozenset(
    {"ужасно", "кошмар", "отвратительно", "невыносимо", "недопустимо", "неприемлемо", "катастрофа"}
)


class Problem(TypedDict):
    category: str
    description: str
    keywords_found: list[str]
    severity: str
    context: str


class ProblemExtractor:
    """Detect complaint categories present in a review's text."""

    def extract(self, text: str | None) -> list[Problem]:
        if not text or not isinstance(text, str):
            return []

        text_lower = text.lower()
        problems: list[Problem] = []

        for category, data in PROBLEM_CATEGORIES.items():
            keywords: list[str] = data["keywords"]  # type: ignore[assignment]
            matches = [kw for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)]
            if not matches:
                continue
            problems.append(
                {
                    "category": category,
                    "description": data["description"],  # type: ignore[typeddict-item]
                    "keywords_found": matches,
                    "severity": self._severity(text_lower, matches),
                    "context": self._context(text, matches[0]),
                }
            )

        return problems

    def _severity(self, text_lower: str, matches: list[str]) -> str:
        has_severe = any(word in text_lower for word in SEVERE_WORDS)
        if has_severe or len(matches) >= 3:
            return "high"
        if len(matches) >= 2:
            return "medium"
        return "low"

    @staticmethod
    def _context(text: str, keyword: str, window: int = 50) -> str:
        index = text.lower().find(keyword.lower())
        if index < 0:
            return ""
        start = max(0, index - window)
        end = min(len(text), index + len(keyword) + window)
        return re.sub(r"\s+", " ", text[start:end]).strip()
