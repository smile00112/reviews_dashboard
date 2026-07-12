"""Unit tests for the rotating proxy pool spec parsing and rotation (offline)."""

from app.scraper.proxy_pool import ProxyPool


def test_empty_spec_is_disabled():
    pool = ProxyPool("")
    assert pool.enabled is False
    assert len(pool) == 0
    assert pool.next() is None
    assert pool.next_requests_proxies() is None


def test_port_range_expands_one_proxy_per_port():
    pool = ProxyPool("socks5://user:pass@host.example:10000-10002")
    assert len(pool) == 3
    assert pool.next() == "socks5://user:pass@host.example:10000"
    assert pool.next() == "socks5://user:pass@host.example:10001"
    assert pool.next() == "socks5://user:pass@host.example:10002"
    # round-robin wraps back to the first
    assert pool.next() == "socks5://user:pass@host.example:10000"


def test_comma_list_and_default_scheme():
    pool = ProxyPool("host.a:8080, http://host.b:9090")
    assert len(pool) == 2
    # bare entry gets the default http:// scheme
    assert pool.next() == "http://host.a:8080"
    assert pool.next() == "http://host.b:9090"


def test_requests_proxies_mapping():
    pool = ProxyPool("socks5://u:p@host:1080")
    assert pool.next_requests_proxies() == {
        "http": "socks5://u:p@host:1080",
        "https": "socks5://u:p@host:1080",
    }


def test_redact_strips_credentials():
    pool = ProxyPool("socks5://secretuser:secretpass@host:1080")
    msg = "error connecting via secretuser:secretpass@host:1080"
    assert "secretuser:secretpass" not in pool.redact(msg)
    assert "***" in pool.redact(msg)
