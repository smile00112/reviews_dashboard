from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/yandex_reviews"
    yandex_operator_login: str = ""
    yandex_operator_password: str = ""
    yandex_storage_state_path: str = ".local/yandex-storage-state.json"
    scraper_debug_dir: str = ".local/scraper-debug"
    api_cors_origins: str = "http://localhost:3000"


settings = Settings()
