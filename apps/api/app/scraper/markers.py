"""Shared bot-protection / captcha markers for all scrapers.

Do NOT include a bare "captcha": it matches the `captchapgrd` fingerprinting
library URL embedded in every Yandex Maps SPA page, so a normal, fully-loaded
review page would false-positive as an access challenge. Use only the markers
that appear on genuine captcha / bot-wall pages.
"""

BOT_MARKERS: tuple[str, ...] = (
    "showcaptcha",
    "SmartCaptcha",
    "Подтвердите, что запросы",
    "Обнаружена защита от ботов",
)
