from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VenueStateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: UUID
    session_id: UUID
    timestamp: datetime
    active_scenario_key: str
    nodes_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    edges_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    assets_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    canonical_input_hash: str = ""
