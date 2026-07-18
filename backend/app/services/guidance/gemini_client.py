from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.config import Settings, settings


class GeminiError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        attempt_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.attempt_count = attempt_count


@dataclass(frozen=True)
class GeminiResponse:
    payload: dict[str, Any]
    request_id: str | None
    attempt_count: int
    latency_ms: int


class GeminiClient:
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        config: Settings = settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    @staticmethod
    def _safe_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return (response.text or "No response detail")[:800]
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            status = error.get("status") or error.get("code")
            message = error.get("message")
            return f"{status}: {message}"[:800]
        return json.dumps(payload, ensure_ascii=False)[:800]

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        texts: list[str] = []
        for step in payload.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for content in step.get("content", []):
                if content.get("type") == "text" and isinstance(
                    content.get("text"), str
                ):
                    texts.append(content["text"])
        if not texts:
            for output in payload.get("outputs", []):
                if output.get("type") == "text" and isinstance(output.get("text"), str):
                    texts.append(output["text"])
        if not texts:
            raise GeminiError("EMPTY_OUTPUT", "Gemini returned no text output.")
        return "".join(texts)

    async def generate(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
    ) -> GeminiResponse:
        if not self.config.gemini_configured:
            raise GeminiError("NOT_CONFIGURED", "Gemini API key is not configured.")
        headers = {
            "x-goog-api-key": self.config.GEMINI_API_KEY or "",
            "Content-Type": "application/json",
            "Api-Revision": self.config.GEMINI_API_REVISION,
        }
        body = {
            "model": self.config.GEMINI_MODEL,
            "input": prompt,
            "store": False,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        }
        retryable = {429, 500, 502, 503, 504}
        max_attempts = self.config.GEMINI_MAX_RETRIES + 1
        start = asyncio.get_running_loop().time()
        if self.config.GEMINI_REQUEST_DELAY_SECONDS:
            await asyncio.sleep(self.config.GEMINI_REQUEST_DELAY_SECONDS)
        async with httpx.AsyncClient(
            timeout=self.config.GEMINI_TIMEOUT_SECONDS,
            transport=self.transport,
        ) as client:
            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    delay = min(30.0, (2 ** (attempt - 2)) + random.random())
                    await asyncio.sleep(delay)
                try:
                    response = await client.post(
                        self.endpoint, headers=headers, json=body
                    )
                except httpx.TimeoutException as exc:
                    if attempt == max_attempts:
                        raise GeminiError(
                            "TIMEOUT",
                            "Gemini request timed out.",
                            attempt_count=attempt,
                        ) from exc
                    continue
                except httpx.RequestError as exc:
                    if attempt == max_attempts:
                        raise GeminiError(
                            "NETWORK_ERROR",
                            "Gemini request failed before receiving a response.",
                            attempt_count=attempt,
                        ) from exc
                    continue
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise GeminiError(
                            "INVALID_RESPONSE",
                            "Gemini returned a non-JSON API response.",
                            attempt_count=attempt,
                        ) from exc
                    if not isinstance(payload, dict):
                        raise GeminiError(
                            "INVALID_RESPONSE",
                            "Gemini returned an unexpected API response shape.",
                            attempt_count=attempt,
                        )
                    text = self._extract_text(payload)
                    try:
                        structured = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise GeminiError(
                            "INVALID_JSON",
                            "Gemini output was not valid JSON.",
                            attempt_count=attempt,
                        ) from exc
                    latency = int((asyncio.get_running_loop().time() - start) * 1000)
                    return GeminiResponse(
                        payload=structured,
                        request_id=payload.get("id"),
                        attempt_count=attempt,
                        latency_ms=latency,
                    )
                detail = self._safe_error(response)
                if response.status_code not in retryable or attempt == max_attempts:
                    raise GeminiError(
                        f"HTTP_{response.status_code}",
                        detail,
                        status_code=response.status_code,
                        attempt_count=attempt,
                    )
        raise GeminiError("UNKNOWN", "Gemini request did not complete.")
