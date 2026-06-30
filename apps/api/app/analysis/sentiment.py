"""Rule-based sentiment classification for Russian review text.

Deterministic and local (constitution Principle VI). Degrades safely: empty / None /
non-string input yields a neutral result and never raises.
"""

from __future__ import annotations

import re
from typing import TypedDict

# Word-boundary matching is used so that, e.g., "плохо" does not match inside
# "неплохо". Multi-word negative phrases (e.g. "не вкусно") are listed explicitly.
POSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "отлично", "прекрасно", "замечательно", "великолепно", "супер",
        "хорошо", "хороший", "хорошая", "хорошее", "хорошие",
        "нравится", "понравилось", "понравился", "понравилась",
        "рекомендую", "советую",
        "вкусно", "вкусный", "вкусная", "вкусное", "вкусные",
        "быстро", "быстрый", "быстрая", "быстрое", "быстрые",
        "вежливо", "вежливый", "вежливая", "вежливое", "вежливые",
        "чисто", "чистый", "чистая", "чистое", "чистые",
        "удобно", "удобный", "удобная", "удобное", "удобные",
        "комфортно", "комфортный", "комфортная", "комфортное",
        "люблю", "обожаю", "восхищаюсь",
        "лучший", "лучшая", "лучшее", "лучшие",
        "отличный", "отличная", "отличное", "отличные",
        "замечательный", "замечательная", "замечательное",
        "прекрасный", "прекрасная", "прекрасное",
        "восхитительный", "восхитительная", "восхитительное",
        "потрясающий", "потрясающая", "потрясающее",
        "шикарно", "шикарный", "шикарная", "шикарное",
        "классно", "классный", "классная", "классное",
        "круто", "крутой", "крутая", "крутое",
        "топовый", "топовая", "топовое",
    }
)

NEGATIVE_WORDS: frozenset[str] = frozenset(
    {
        "плохо", "плохой", "плохая", "плохое", "плохие",
        "ужасно", "ужасный", "ужасная", "ужасное", "ужасные",
        "отвратительно", "отвратительный", "отвратительная", "отвратительное",
        "не нравится", "не понравилось", "не понравился", "не понравилась",
        "не рекомендую", "не советую",
        "не вкусно", "невкусно", "невкусный", "невкусная", "невкусное",
        "медленно", "медленный", "медленная", "медленное", "медленные",
        "грубо", "грубый", "грубая", "грубое", "грубые",
        "грязно", "грязный", "грязная", "грязное", "грязные",
        "неудобно", "неудобный", "неудобная", "неудобное",
        "некомфортно", "некомфортный", "некомфортная",
        "ненавижу", "терпеть не могу",
        "худший", "худшая", "худшее", "худшие",
        "кошмар", "кошмарный", "кошмарная", "кошмарное",
        "ужас", "разочарован", "разочарована", "разочарованы",
        "жаль", "жалко",
        "проблема", "проблемы", "проблемный", "проблемная",
        "жалоба", "жалобы", "жалуюсь",
        "недоволен", "недовольна", "недовольно", "недовольны",
        "долго", "долгий", "долгая", "долгое",
        "дорого", "дорогой", "дорогая", "дорогое",
        "обманули", "обманул", "обманула",
        "не работает", "не работал", "не работала",
        "сломалось", "сломался", "сломалась",
        "не приехал", "не приехала", "не привезли",
    }
)

INTENSIFIERS: frozenset[str] = frozenset(
    {
        "очень", "крайне", "чрезвычайно", "невероятно",
        "абсолютно", "совершенно", "полностью", "вполне",
        "совсем", "вовсе", "вообще",
        "особенно", "исключительно", "необычайно",
    }
)


class SentimentResult(TypedDict):
    sentiment: str
    score: float
    confidence: float
    positive_count: int
    negative_count: int
    intensifier_count: int


def _count(text_lower: str, terms: frozenset[str]) -> int:
    count = 0
    for term in terms:
        # \b word boundaries; terms may contain spaces (multi-word phrases).
        if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
            count += 1
    return count


def _strip(text_lower: str, terms: frozenset[str]) -> str:
    """Blank out matched terms so a negated phrase ("не вкусно") does not also
    count its embedded positive word ("вкусно")."""
    for term in terms:
        text_lower = re.sub(r"\b" + re.escape(term) + r"\b", " ", text_lower)
    return text_lower


class SentimentAnalyzer:
    """Classify text as positive / negative / neutral via term dictionaries."""

    NEUTRAL: SentimentResult = {
        "sentiment": "neutral",
        "score": 0.0,
        "confidence": 0.0,
        "positive_count": 0,
        "negative_count": 0,
        "intensifier_count": 0,
    }

    def analyze(self, text: str | None) -> SentimentResult:
        if not text or not isinstance(text, str):
            return dict(self.NEUTRAL)  # type: ignore[return-value]

        text_lower = text.lower()
        negative = _count(text_lower, NEGATIVE_WORDS)
        # Count positives only after removing negative phrases, so negated
        # positives ("не нравится", "не вкусно") are not double-counted.
        positive = _count(_strip(text_lower, NEGATIVE_WORDS), POSITIVE_WORDS)
        intensifiers = _count(text_lower, INTENSIFIERS)

        total = positive + negative
        if total == 0 or positive == negative:
            sentiment, score = "neutral", 0.0
        elif positive > negative:
            sentiment, score = "positive", (positive - negative) / total
        else:
            sentiment, score = "negative", -(negative - positive) / total

        if intensifiers and score:
            score *= 1 + intensifiers * 0.2
            score = max(-1.0, min(1.0, score))

        confidence = min(1.0, total / 10.0)

        return {
            "sentiment": sentiment,
            "score": round(score, 3),
            "confidence": round(confidence, 3),
            "positive_count": positive,
            "negative_count": negative,
            "intensifier_count": intensifiers,
        }
