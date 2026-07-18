from __future__ import annotations

import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.services.guidance import gemini_client as module
from backend.app.services.guidance.gemini_client import GeminiClient, GeminiError


def configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "ENVIRONMENT": "test",
        "ALLOW_SQLITE_TESTS": True,
        "GEMINI_API_KEY": "AIza" + "A" * 32,
        "GEMINI_MAX_RETRIES": 0,
        "GEMINI_REQUEST_DELAY_SECONDS": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


async def test_gemini_interactions_request_and_structured_response() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("x-goog-api-key")
        seen["revision"] = request.headers.get("Api-Revision")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "interaction-123",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": '{"result":"OK"}'}],
                    }
                ],
            },
        )

    client = GeminiClient(configured_settings(), transport=httpx.MockTransport(handler))
    result = await client.generate(prompt="Return OK", schema={"type": "object"})

    assert result.payload == {"result": "OK"}
    assert result.request_id == "interaction-123"
    assert result.attempt_count == 1
    assert seen["url"] == GeminiClient.endpoint
    assert str(seen["api_key"]).startswith("AIza")
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "gemini-3.5-flash"
    assert body["store"] is False
    assert body["response_format"]["mime_type"] == "application/json"


async def test_gemini_retries_429_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(module.random, "random", lambda: 0.0)

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}},
            )
        return httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "{}"}],
                    }
                ]
            },
        )

    client = GeminiClient(
        configured_settings(GEMINI_MAX_RETRIES=1),
        transport=httpx.MockTransport(handler),
    )
    result = await client.generate(prompt="test", schema={"type": "object"})
    assert calls == 2
    assert result.attempt_count == 2


async def test_gemini_invalid_json_is_rejected() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "not-json"}],
                    }
                ]
            },
        )

    client = GeminiClient(configured_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GeminiError, match="valid JSON") as error:
        await client.generate(prompt="test", schema={"type": "object"})
    assert error.value.code == "INVALID_JSON"


async def test_gemini_requires_configured_key() -> None:
    client = GeminiClient(configured_settings(GEMINI_API_KEY=None))
    with pytest.raises(GeminiError) as error:
        await client.generate(prompt="test", schema={"type": "object"})
    assert error.value.code == "NOT_CONFIGURED"


async def test_gemini_network_error_is_normalized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    client = GeminiClient(configured_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GeminiError) as error:
        await client.generate(prompt="test", schema={"type": "object"})
    assert error.value.code == "NETWORK_ERROR"


async def test_gemini_rejects_non_json_api_response() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not an API object")

    client = GeminiClient(configured_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GeminiError) as error:
        await client.generate(prompt="test", schema={"type": "object"})
    assert error.value.code == "INVALID_RESPONSE"
