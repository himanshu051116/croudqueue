from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Authoritative application settings.

    PostgreSQL remains the only supported runtime database. SQLite is allowed only
    when both ``ENVIRONMENT=test`` and ``ALLOW_SQLITE_TESTS=true`` are supplied,
    which keeps fast API tests independent from the deployment contract.
    """

    DATABASE_URL: str = Field(
        "postgresql+psycopg://postgres:postgres@localhost:54321/crowdcue"
    )
    DATABASE_POOL_SIZE: int = Field(2, ge=1, le=20)
    DATABASE_MAX_OVERFLOW: int = Field(0, ge=0, le=20)
    DATABASE_POOL_TIMEOUT_SECONDS: float = Field(10.0, gt=0, le=120)
    DATABASE_POOL_RECYCLE_SECONDS: int = Field(300, ge=30, le=3600)
    REDIS_URL: str = "redis://localhost:63791/0"
    REDIS_REQUIRED: bool = False

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_API_REVISION: str = "2026-05-20"
    GEMINI_TIMEOUT_SECONDS: float = Field(60.0, gt=0, le=300)
    GEMINI_MAX_RETRIES: int = Field(3, ge=0, le=8)
    GEMINI_REQUEST_DELAY_SECONDS: float = Field(0.0, ge=0, le=60)
    GEMINI_SCENARIO_COOLDOWN_SECONDS: float = Field(2.0, ge=0, le=300)

    ENABLE_DEMO_FAULT_INJECTION: bool = False

    SECRET_KEY: str = "development-only-change-me-please-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=1440)
    ALLOWED_CORS_ORIGINS: str = '["http://localhost:5173","http://127.0.0.1:5173"]'

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    ALLOW_SQLITE_TESTS: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @field_validator("GEMINI_MODEL")
    @classmethod
    def validate_model_target(cls, value: str) -> str:
        normalized = value.strip().lower()
        forbidden = {"gemini-1.5-flash", "gemini-flash-latest"}
        if normalized in forbidden or normalized.endswith("-latest"):
            raise ValueError("Use a pinned Gemini model ID, not a moving alias.")
        if not normalized.startswith("gemini-"):
            raise ValueError("GEMINI_MODEL must be a Gemini model identifier.")
        return value.strip()

    @field_validator("ENVIRONMENT")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production.")
        return normalized

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "Settings":
        is_sqlite = self.DATABASE_URL.startswith("sqlite")
        if is_sqlite and not (self.ENVIRONMENT == "test" and self.ALLOW_SQLITE_TESTS):
            raise ValueError(
                "SQLite is test-only. Runtime and integration deployments require "
                "PostgreSQL."
            )
        if self.ENVIRONMENT == "production":
            if len(self.SECRET_KEY) < 32 or "development-only" in self.SECRET_KEY:
                raise ValueError("Production SECRET_KEY must be securely configured.")
            if self.ENABLE_DEMO_FAULT_INJECTION:
                raise ValueError("Demo fault injection must be disabled in production.")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not allowed with credentials.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        try:
            parsed: Any = json.loads(self.ALLOWED_CORS_ORIGINS)
        except json.JSONDecodeError as exc:
            raise ValueError("ALLOWED_CORS_ORIGINS must be a JSON array.") from exc
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError("ALLOWED_CORS_ORIGINS must be a JSON array of strings.")
        return [item.rstrip("/") for item in parsed]

    @property
    def gemini_configured(self) -> bool:
        key = (self.GEMINI_API_KEY or "").strip()
        return bool(key and not key.lower().startswith(("dummy", "replace", "test")))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
