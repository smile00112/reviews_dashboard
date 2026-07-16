"""Rotating HTTP proxy pool for the requests-based scrapers.

Parses the ``proxy_pool`` setting into a list of ``http://user:pass@host:port``
URLs and hands them out round-robin. Introduced to replace the exhausted ScrapeOps
proxy on the 2GIS transport: 2GIS short links and JSON APIs 403 from a datacenter IP,
so each request is routed through a rotating residential/DC proxy and retried on the
next proxy when one is blocked.

Credentials come only from ``.env`` via settings (constitution VIII); this module
never carries a default pool and redacts the pool's password out of error strings.
"""

from __future__ import annotations

import itertools
import threading


def _parse_spec(spec: str) -> list[str]:
    """Expand a pool spec into a list of proxy URLs.

    Each comma-separated entry is ``user:pass@host:port`` where ``port`` may be a
    range ``p1-p2`` (inclusive) that expands to one proxy per port. A missing scheme
    defaults to ``http://``.
    """
    proxies: list[str] = []
    for raw in spec.split(","):
        entry = raw.strip()
        if not entry:
            continue
        scheme = "http://"
        if "://" in entry:
            scheme, entry = entry.split("://", 1)
            scheme += "://"
        # Split the trailing :port(-range) off the right; host may follow an @.
        creds_host, _, port_part = entry.rpartition(":")
        if not port_part:
            proxies.append(scheme + entry)
            continue
        if "-" in port_part:
            start_s, _, end_s = port_part.partition("-")
            try:
                start, end = int(start_s), int(end_s)
            except ValueError:
                proxies.append(scheme + entry)
                continue
            for port in range(start, end + 1):
                proxies.append(f"{scheme}{creds_host}:{port}")
        else:
            proxies.append(f"{scheme}{creds_host}:{port_part}")
    return proxies


class ProxyPool:
    """Thread-safe round-robin pool of proxy URLs."""

    def __init__(self, spec: str) -> None:
        self._proxies = _parse_spec(spec)
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)

    def __len__(self) -> int:
        return len(self._proxies)

    def next(self) -> str | None:
        """Return the next proxy URL round-robin, or None if the pool is empty."""
        if self._cycle is None:
            return None
        with self._lock:
            return next(self._cycle)

    def next_requests_proxies(self) -> dict[str, str] | None:
        """Next proxy as a requests ``proxies=`` mapping, or None if empty."""
        proxy = self.next()
        if proxy is None:
            return None
        return {"http": proxy, "https": proxy}

    def next_playwright_proxy(self) -> dict[str, str] | None:
        """Next proxy as a Playwright ``proxy=`` mapping, or None if empty.

        Playwright wants credentials split out of the server URL (``server``/
        ``username``/``password``), unlike ``requests`` which takes them embedded.
        """
        proxy = self.next()
        if proxy is None:
            return None
        scheme, _, rest = proxy.partition("://")
        creds, _, host = rest.rpartition("@")
        if not creds:
            return {"server": proxy}
        user, _, password = creds.partition(":")
        return {"server": f"{scheme}://{host}", "username": user, "password": password}

    def redact(self, text: str) -> str:
        """Strip proxy credentials (``user:pass@``) from a message before logging."""
        for proxy in self._proxies:
            if "@" in proxy:
                creds = proxy.split("://", 1)[-1].split("@", 1)[0]
                if creds:
                    text = text.replace(creds, "***")
        return text
