"""Feature 010 / US6: single shared bot-marker definition across scrapers."""

from app.scraper import markers, twogis_api, yandex_http, yandex_public, yandex_scrapeops


def test_yandex_scrapers_share_the_base_tuple():
    assert yandex_public.CAPTCHA_MARKERS is markers.BOT_MARKERS
    assert yandex_http.BOT_MARKERS is markers.BOT_MARKERS
    assert yandex_scrapeops.BOT_MARKERS is markers.BOT_MARKERS


def test_twogis_extends_the_base_tuple():
    assert set(markers.BOT_MARKERS).issubset(set(twogis_api.BOT_MARKERS))
    assert "Доступ ограничен" in twogis_api.BOT_MARKERS
    assert "Access Denied" in twogis_api.BOT_MARKERS


def test_no_bare_captcha_marker():
    # A bare "captcha" matches the captchapgrd fingerprinting URL on every
    # Yandex Maps page and must never be a marker.
    assert "captcha" not in {m.lower() for m in markers.BOT_MARKERS}
