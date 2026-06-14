from app.scraper.normalize import build_review_hash, normalize_text


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  hello   world  ") == "hello world"


def test_normalize_text_empty_author():
    assert normalize_text(None) == ""
    assert normalize_text("", lowercase=True) == ""


def test_build_review_hash_same_with_different_spacing():
    h1 = build_review_hash("Ivan", 5, "2 января", "Отличное место")
    h2 = build_review_hash("  Ivan  ", 5, "  2   января ", "  Отличное   место ")
    assert h1 == h2


def test_build_review_hash_different_ratings():
    h1 = build_review_hash("Ivan", 5, "2 января", "Отличное место")
    h2 = build_review_hash("Ivan", 4, "2 января", "Отличное место")
    assert h1 != h2


def test_normalize_text_preserves_cyrillic_in_review():
    assert normalize_text("  Привет   мир  ", lowercase=False) == "Привет мир"
    assert normalize_text("  Ivan  ", lowercase=True) == "ivan"
