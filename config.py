"""
Centralized application configuration.

All values are read from environment variables (or a `.env` file in local
development). See `.env.example` for the full list of supported variables.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_name: str = "URL Shortener"
    base_url: str = "http://localhost:8000"
    environment: str = "development"

    # --- Database ---
    database_url: str = "postgresql://shortener:shortener@localhost:5432/shortener"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---
    secret_key: str = "insecure-dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Rate limiting ---
    rate_limit_per_minute: int = 60
    rate_limit_redirect_per_minute: int = 300

    # --- Short codes ---
    short_code_length: int = 7


@lru_cache
def get_settings() -> Settings:
    """Settings are cached so the environment is only parsed once per process."""
    return Settings()
