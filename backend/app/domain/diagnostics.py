from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticSeverity(str, Enum):
    INFO = "INFO"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class DiagnosticStage(str, Enum):
    SCHEMA = "SCHEMA"
    REVERSE_COMPILE = "REVERSE_COMPILE"
    SEMANTIC_EQUIVALENCE = "SEMANTIC_EQUIVALENCE"
    ACCESSIBILITY = "ACCESSIBILITY"
    COLLISION = "COLLISION"
    SIMULATION = "SIMULATION"
    SYSTEM = "SYSTEM"


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: DiagnosticSeverity
    stage: DiagnosticStage
    code: str
    message: str
    language: str | None = None
    channel: str | None = None
    clause: str | None = None
    expected: Any = None
    actual: Any = None
    details: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = False
