from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID


def _normalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_normalize(item) for item in value), key=str)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def domain_hash(domain: str, value: Any) -> str:
    hasher = hashlib.sha256()
    hasher.update(domain.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(canonical_json_bytes(value))
    return hasher.hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
