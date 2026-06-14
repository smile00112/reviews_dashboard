import re
from urllib.parse import urlparse, urlunparse

YANDEX_URL_PATTERN = re.compile(
    r"^https://(?:yandex\.(?:ru|com)|[^/]*yandex\.[^/]+)/maps/",
    re.IGNORECASE,
)


def validate_yandex_url(url: str) -> None:
    if not YANDEX_URL_PATTERN.match(url.strip()):
        raise ValueError("URL must be a Yandex Maps organization URL")


def normalize_yandex_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    normalized = urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))
    return normalized


def extract_external_id(url: str) -> str | None:
    match = re.search(r"/org/[^/]+/(\d+)", url)
    return match.group(1) if match else None
