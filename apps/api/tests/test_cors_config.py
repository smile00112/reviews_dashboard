"""Feature 010 / US6: CORS fails closed — empty origin list aborts startup."""

import pytest

from app.main import _cors_origins


def test_empty_origins_raise():
    with pytest.raises(RuntimeError, match="API_CORS_ORIGINS"):
        _cors_origins("")


def test_whitespace_only_origins_raise():
    with pytest.raises(RuntimeError, match="refusing to fall back"):
        _cors_origins(" , ,")


def test_normal_origins_parse():
    assert _cors_origins("http://localhost:3000, https://dash.example.com") == [
        "http://localhost:3000",
        "https://dash.example.com",
    ]
