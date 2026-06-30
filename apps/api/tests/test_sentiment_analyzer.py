import pytest

from app.analysis.sentiment import SentimentAnalyzer

analyzer = SentimentAnalyzer()


def test_positive_review():
    result = analyzer.analyze("Очень вкусно, отличное обслуживание и чисто")
    assert result["sentiment"] == "positive"
    assert result["score"] > 0


def test_negative_review():
    result = analyzer.analyze("Ужасно долго ждали, еда холодная и грязно")
    assert result["sentiment"] == "negative"
    assert result["score"] < 0


def test_negation_is_negative_not_positive():
    # "не вкусно" / "не понравилось" must not count the embedded positive word.
    result = analyzer.analyze("Совсем не вкусно, не понравилось")
    assert result["sentiment"] == "negative"
    assert result["positive_count"] == 0


def test_neutral_when_no_signal():
    result = analyzer.analyze("Был здесь в среду после обеда")
    assert result["sentiment"] == "neutral"
    assert result["score"] == 0.0


def test_intensifier_amplifies_score():
    base = analyzer.analyze("вкусно")
    amplified = analyzer.analyze("очень вкусно")
    assert abs(amplified["score"]) >= abs(base["score"])
    assert amplified["intensifier_count"] == 1


@pytest.mark.parametrize("bad", [None, "", "   ", 123])
def test_safe_degrade_never_raises(bad):
    result = analyzer.analyze(bad)  # type: ignore[arg-type]
    assert result["sentiment"] == "neutral"
    assert result["score"] == 0.0


def test_score_bounded():
    result = analyzer.analyze("очень очень очень отлично прекрасно великолепно вкусно чисто удобно")
    assert -1.0 <= result["score"] <= 1.0
