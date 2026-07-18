from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Language(str, Enum):
    EN = "en"
    ES = "es"
    FR = "fr"


class GuidanceChannel(str, Enum):
    FAN_APP = "fan_app"
    PA = "pa"


class GuidanceVariant(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    channel: GuidanceChannel
    version: int = Field(1, ge=1)
    audience_action: str
    route_clause: str
    fallback_clause: str
    protection_clause: str
    validity_clause: str
    optional_explanation: str | None = None
    rendered_text: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CompiledMeaning(BaseModel):
    model_config = ConfigDict(frozen=True)

    audience_sections: tuple[str, ...] = ()
    approach_zones: tuple[str, ...] = ()
    action: str | None = None
    directive_strength: str | None = None
    destination_id: str | None = None
    all_mentioned_destinations: tuple[str, ...] = ()
    route: tuple[str, ...] = ()
    excluded_cohorts: tuple[str, ...] = ()
    fallback_action: str | None = None
    fallback_destination_id: str | None = None
    effective_time: datetime | None = None
    expiry_time: datetime | None = None
    closure_claims: tuple[str, ...] = ()
    waiting_claims: tuple[str, ...] = ()
    unsupported_numeric_claims: tuple[str, ...] = ()
    negated_destinations: tuple[str, ...] = ()
    raw_evidence: dict[str, Any] = Field(default_factory=dict)


class GuidanceBatch(BaseModel):
    """Strict six-variant model output contract."""

    variants: tuple[GuidanceVariant, ...]

    @model_validator(mode="after")
    def validate_matrix(self) -> "GuidanceBatch":
        expected = {
            (language.value, channel.value)
            for language in Language
            for channel in GuidanceChannel
        }
        actual = {(item.language.value, item.channel.value) for item in self.variants}
        if actual != expected or len(self.variants) != 6:
            raise ValueError(
                "Guidance output must contain exactly six unique variants."
            )
        return self
