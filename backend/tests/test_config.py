import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_settings_valid_model():
    # Valid model config
    s = Settings(
        DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/crowdcue",
        REDIS_URL="redis://localhost:6379/0",
        GEMINI_API_KEY="test_key",
        GEMINI_MODEL="gemini-3.5-flash",
        SECRET_KEY="testsecret",
    )
    assert s.GEMINI_MODEL == "gemini-3.5-flash"


def test_settings_invalid_model():
    # Invalid model configurations should raise ValueError via field_validator
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/crowdcue",
            REDIS_URL="redis://localhost:6379/0",
            GEMINI_API_KEY="test_key",
            GEMINI_MODEL="gemini-1.5-flash",  # Forbidden
            SECRET_KEY="testsecret",
        )
    assert "pinned Gemini model ID" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        Settings(
            DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/crowdcue",
            REDIS_URL="redis://localhost:6379/0",
            GEMINI_API_KEY="test_key",
            GEMINI_MODEL="gemini-flash-latest",  # Forbidden
            SECRET_KEY="testsecret",
        )
    assert "pinned Gemini model ID" in str(excinfo.value)


def test_settings_cors_no_wildcard_with_credentials():
    # Verify that ALLOWED_CORS_ORIGINS defaults to specific origins and never wildcard *
    s = Settings()
    assert "*" not in s.cors_origins
    assert len(s.cors_origins) > 0
    for origin in s.cors_origins:
        assert origin != "*"


def test_production_rejects_demo_fault_injection() -> None:
    with pytest.raises(ValidationError, match="must be disabled in production"):
        Settings(
            _env_file=None,
            DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/crowdcue",
            ENVIRONMENT="production",
            SECRET_KEY="x" * 48,
            ENABLE_DEMO_FAULT_INJECTION=True,
        )


def test_serverless_pool_defaults_are_conservative() -> None:
    settings = Settings(_env_file=None)
    assert settings.DATABASE_POOL_SIZE == 2
    assert settings.DATABASE_MAX_OVERFLOW == 0
    assert settings.REDIS_REQUIRED is False
