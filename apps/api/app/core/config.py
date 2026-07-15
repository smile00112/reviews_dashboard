from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/yandex_reviews"
    yandex_operator_login: str = ""
    yandex_operator_password: str = ""
    yandex_storage_state_path: str = ".local/yandex-storage-state.json"
    scraper_debug_dir: str = ".local/scraper-debug"
    api_cors_origins: str = "http://localhost:3000"

    # Admin panel (feature 004)
    admin_secret_key: str
    session_max_age: int = 43200  # 12 hours

    # Network overview dashboard (feature 009). SLA threshold for the "answered
    # within SLA" share; response time is the response_first_seen_at proxy.
    overview_sla_threshold_minutes: int = 1440  # 24h

    # Browserless HTTP scraper (public_http mode, feature 003)
    http_scrape_limit: int = 150
    http_scrape_max_pages: int = 5
    http_scrape_delay_seconds: float = 2.0
    http_scrape_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Sprav cabinet reader (feature 011, console-only). Read-only: the cabinet
    # entry point is settings-driven so a URL change is a config edit. The
    # cabinet redirects /sprav/ -> /sprav/companies and inlines the list.
    sprav_companies_url: str = "https://yandex.ru/sprav/"
    sprav_orgs_output_path: str = ".local/sprav-orgs.json"
    sprav_page_timeout_ms: int = 90000

    # ScrapeOps proxy scraper (scrapeops mode, feature 005)
    scrapeops_api_key: str = ""
    scrapeops_limit: int = 150
    scrapeops_max_pages: int = 5
    # Yandex /reviews/?lang=ru is server-rendered, so JS rendering is unnecessary
    # and costs ~10x ScrapeOps credits. Leave off; flip on only if a target needs it.
    scrapeops_render_js: bool = False

    # 2GIS reviews API scraper (twogis_api mode, feature 006). Both keys are the
    # public keys embedded in the 2GIS web client; kept in settings so a block can
    # be resolved by rotating the value (a blocked key surfaces as needs_manual_action).
    twogis_catalog_key: str = "rubnkm7490"
    twogis_review_key: str = "6e7e1929-4ea9-4a5d-8c05-d601860389bd"
    twogis_review_limit: int = 150
    twogis_page_size: int = 50
    twogis_request_delay_seconds: float = 0.3

    # Rotating HTTP proxy pool (feature: 2GIS proxy rotation). Replaces the exhausted
    # ScrapeOps proxy for the requests-based 2GIS transport. Credentials live only in
    # .env (constitution VIII) — never commit a populated value. Comma-separated list
    # of `user:pass@host:port` entries; a port RANGE `p1-p2` expands to one proxy per
    # port, e.g. `user:pass@pool.proxys.io:10000-10022`. Scheme defaults to http://.
    proxy_pool: str = ""
    # How many distinct pool proxies to try before giving up on a single request.
    proxy_pool_max_tries: int = 4

    # Google Sheets ratings export (operator script, scripts/sync_ratings_to_sheet.py).
    # Service-account key is gitignored under .local/ like other local secrets.
    google_sheets_credentials_path: str = ".local/credentials.json"
    google_sheets_spreadsheet_id: str = "1T4IS8-P5YoGAfkFicSu43iLT0-qPtRtTPBpw0VoSKQI"
    google_sheets_worksheet_gid: int = 1208334728


settings = Settings()
