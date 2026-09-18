"""Runtime configuration, read from the environment and an optional backend/.env file."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://fieldwise:fieldwise@localhost:5432/fieldwise"
    redis_url: str = "redis://localhost:6379/0"
    storage_url: str = "file://./data/storage"

    llm_provider: Literal["anthropic", "openai", "fake"] = "anthropic"
    llm_cassette_mode: Literal["off", "record", "replay"] = "off"
    llm_cassette_dir: str = "evals/cassettes"
    default_model: str = "claude-sonnet-5"
    default_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    anthropic_api_key: str | None = Field(default=None, repr=False)
    # Any OpenAI-compatible endpoint: OpenRouter (https://openrouter.ai/api/v1),
    # Ollama (http://localhost:11434/v1), OpenAI itself.
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: str | None = Field(default=None, repr=False)

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
