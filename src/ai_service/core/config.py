"""Environment settings; no external service is required to load them."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Electronics AI Service"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = Field(default=8001, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    backend_api_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    backend_api_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)

    llm_api_key: SecretStr | None = None
    llm_base_url: AnyHttpUrl | None = None
    llm_model: str | None = None
    llm_timeout: float = Field(default=30, gt=0, allow_inf_nan=False)

    @field_validator("llm_api_key", "llm_base_url", "llm_model", mode="before")
    @classmethod
    def normalize_optional_llm_settings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
