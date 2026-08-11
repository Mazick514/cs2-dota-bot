from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read exclusively from environment variables/.env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    bot_token: SecretStr
    pandascore_api_key: SecretStr = Field(validation_alias=AliasChoices("PANDASCORE_API_KEY", "CS2_API_KEY"))
    liquipedia_user_agent: str = "CS2-Dota-Telegram-Bot/1.0 (contact: YOUR_CONTACT_URL_OR_EMAIL)"
    liquipedia_cache_ttl_seconds: int = 300
    liquipedia_min_request_interval_seconds: float = 2.0
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    match_poll_interval_seconds: int = 60
    log_level: str = "INFO"

    @field_validator("bot_token", "pandascore_api_key")
    @classmethod
    def secrets_must_not_be_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @property
    def cs2_api_key(self) -> SecretStr:
        """Compatibility accessor for callers migrating from the CS2-only configuration."""
        return self.pandascore_api_key

    @field_validator("match_poll_interval_seconds")
    @classmethod
    def poll_interval_must_be_positive(cls, value: int) -> int:
        if value < 15:
            raise ValueError("must be at least 15 seconds to respect API limits")
        return value

    @field_validator("liquipedia_user_agent")
    @classmethod
    def liquipedia_user_agent_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("liquipedia_cache_ttl_seconds")
    @classmethod
    def liquipedia_cache_ttl_must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be at least 1 second")
        return value

    @field_validator("liquipedia_min_request_interval_seconds")
    @classmethod
    def liquipedia_request_interval_must_follow_terms(cls, value: float) -> float:
        if value < 2:
            raise ValueError("must be at least 2 seconds to comply with Liquipedia MediaWiki API terms")
        return value
