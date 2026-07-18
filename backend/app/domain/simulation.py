from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimulationVerdict(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class FlowMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    maximum_queue: float = Field(ge=0)
    overload_frequency: float = Field(ge=0, le=1)
    unfinished_demand: float = Field(ge=0)
    clearance_time_minutes: float = Field(ge=0)


class PairedSimulationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_set_id: str
    seed: int
    sample_count: int = Field(ge=1)
    paired: bool = True
    baseline: FlowMetrics
    intervention: FlowMetrics
    protected_route_violations: int = Field(ge=0)
    failure_frequency: float = Field(ge=0, le=1)
    wilson_95_lower: float = Field(ge=0, le=1)
    wilson_95_upper: float = Field(ge=0, le=1)
    verdict: SimulationVerdict
    explanation: str
    samples_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_summary: dict[str, Any] = Field(default_factory=dict)
