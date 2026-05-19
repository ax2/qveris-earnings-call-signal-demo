from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or local .env files."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qveris_api_key: str = Field(default="", validation_alias="QVERIS_API_KEY")
    qveris_base_url: str = Field(
        default="https://qveris.ai/api/v1",
        validation_alias="QVERIS_BASE_URL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

