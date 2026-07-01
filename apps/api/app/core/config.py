from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/yandex_reviews"
    yandex_operator_login: str = ""
    yandex_operator_password: str = ""
    yandex_storage_state_path: str = ".local/yandex-storage-state.json"
    scraper_debug_dir: str = ".local/scraper-debug"
    api_cors_origins: str = "http://localhost:3000"

    # Browserless HTTP scraper (public_http mode, feature 003)
    http_scrape_limit: int = 150
    http_scrape_max_pages: int = 5
    http_scrape_delay_seconds: float = 2.0
    http_scrape_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


settings = Settings()
