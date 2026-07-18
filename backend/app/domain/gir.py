from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.workflow import DirectiveStrength, LifecycleState


class DirectiveAction(str, Enum):
    REDIRECT = "REDIRECT"
    CONTINUE = "CONTINUE"
    HOLD = "HOLD"
    AVOID = "AVOID"


class AudienceScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    sections: tuple[str, ...]
    approach_zones: tuple[str, ...]
    cohort_id: str = "general-cohort"


class Directive(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: DirectiveAction
    strength: DirectiveStrength


class FallbackPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: DirectiveAction
    destination_id: str | None = None
    non_target_action: str = "CONTINUE_TO_ASSIGNED_ENTRY"


class GIR(BaseModel):
    """Authoritative Guidance Intermediate Representation."""

    model_config = ConfigDict(frozen=True)

    instruction_id: UUID
    version: int = Field(ge=1)
    venue_id: UUID
    session_id: UUID
    intent_id: UUID
    candidate_id: UUID
    venue_state_snapshot_id: UUID
    reference_data_version: str
    terminology_version: str
    simulation_policy_version: str
    intervention_policy_version: str = "v1.0.0"
    compiler_version: str = "v2.0.0"
    source_team: str = Field(min_length=2, max_length=100)
    audience: AudienceScope
    directive: Directive
    destination_id: str
    route: tuple[str, ...]
    excluded_cohorts: tuple[str, ...] = ()
    protected_route_ids: tuple[str, ...] = ()
    required_asset_ids: tuple[str, ...] = ()
    fallback: FallbackPolicy
    effective_time: datetime
    expiry_time: datetime
    lifecycle_state: LifecycleState
    content_hash: str = ""

    @model_validator(mode="after")
    def validate_contract(self) -> "GIR":
        if self.expiry_time <= self.effective_time:
            raise ValueError("GIR expiry_time must be after effective_time.")
        for value in (self.effective_time, self.expiry_time):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("GIR validity timestamps must be timezone-aware.")
        if self.effective_time.astimezone(timezone.utc).utcoffset() is None:
            raise ValueError("GIR timestamps must be convertible to UTC.")
        if not self.route:
            raise ValueError("GIR route must contain at least one waypoint.")
        return self
