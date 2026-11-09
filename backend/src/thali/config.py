from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="THALI_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    provider_base_url: str = "http://127.0.0.1:8000/mock"
    providers_in_process: bool = False
    provider_timeout_ms: int = 1500
    fetch_deadline_ms: int = 2000
    retry_backoff_min_ms: int = 100
    retry_backoff_max_ms: int = 200
    breaker_failures: int = 3
    breaker_cooldown_s: float = 30.0
    groq_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("GROQ_API_KEY", "THALI_GROQ_API_KEY")
    )
    llm_model: str = "openai/gpt-oss-20b"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_ms: int = 3000
    llm_rpm: int = 6
    llm_cache_size: int = 256
    mock_slow_ms: int = 800
    mock_timeout_sleep_ms: int = 5000
    enable_fault_api: bool = True
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    static_dir: str | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
