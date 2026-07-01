from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def ensure_debug_dir() -> Path:
    path = Path(settings.scraper_debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_debug_artifacts(page, prefix: str) -> tuple[str | None, str | None]:
    debug_dir = ensure_debug_dir()
    run_id = uuid4().hex[:8]
    screenshot_path = debug_dir / f"{prefix}-{run_id}.png"
    html_path = debug_dir / f"{prefix}-{run_id}.html"

    screenshot_str: str | None = None
    html_str: str | None = None

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_str = str(screenshot_path)
    except Exception:
        pass

    try:
        html_path.write_text(page.content(), encoding="utf-8")
        html_str = str(html_path)
    except Exception:
        pass

    return screenshot_str, html_str


def save_html_debug(html: str, prefix: str) -> str | None:
    """Save an HTML snapshot without a browser page (for the HTTP scraper)."""
    debug_dir = ensure_debug_dir()
    run_id = uuid4().hex[:8]
    html_path = debug_dir / f"{prefix}-{run_id}.html"
    try:
        html_path.write_text(html or "", encoding="utf-8")
        return str(html_path)
    except Exception:
        return None
