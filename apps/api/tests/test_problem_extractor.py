import pytest

from app.analysis.problems import ProblemExtractor

extractor = ProblemExtractor()


def _categories(text):
    return {p["category"] for p in extractor.extract(text)}


def test_detects_waiting_and_food_quality():
    cats = _categories("Очень долго ждать, еда холодная и невкусно")
    assert "ожидание" in cats
    assert "качество_еды" in cats


def test_detects_cleanliness():
    assert "чистота" in _categories("Грязно, грязная посуда и неприятный запах")


def test_detects_price():
    assert "цены" in _categories("Слишком дорого, неоправданно дорого за такое")


def test_no_problems_in_positive_text():
    assert extractor.extract("Всё отлично, очень понравилось") == []


def test_severity_high_with_severe_word():
    problems = extractor.extract("Ужасно грязно, грязная посуда повсюду")
    cleanliness = next(p for p in problems if p["category"] == "чистота")
    assert cleanliness["severity"] == "high"


def test_problem_has_context_and_keywords():
    problems = extractor.extract("Официант грубый и невежливый")
    service = next(p for p in problems if p["category"] == "обслуживание")
    assert service["keywords_found"]
    assert service["context"]


@pytest.mark.parametrize("bad", [None, "", "   ", 123])
def test_safe_degrade_never_raises(bad):
    assert extractor.extract(bad) == []  # type: ignore[arg-type]
