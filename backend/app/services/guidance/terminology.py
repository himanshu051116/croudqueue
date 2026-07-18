from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from backend.app.domain.gir import GIR
from backend.app.domain.guidance import Language

TERMINOLOGY_PATH = (
    Path(__file__).resolve().parents[4] / "reference_data" / "terminology.json"
)


@lru_cache(maxsize=1)
def load_terminology() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(TERMINOLOGY_PATH.read_text("utf-8")))


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_literals(gir: GIR, language: Language) -> dict[str, str]:
    terms = load_terminology()["languages"][language.value]
    section_range = "–".join((gir.audience.sections[0], gir.audience.sections[-1]))
    sections = f"{terms['sections_prefix']} {section_range}"
    approach_key = gir.audience.approach_zones[0]
    route_literal = " -> ".join(gir.route)
    return {
        "sections": sections,
        "approach": terms["approach"][approach_key],
        "action": terms["action"][gir.directive.action.value],
        "strength": terms["strength"][gir.directive.strength.value],
        "destination": terms["destinations"][gir.destination_id],
        "fallback_destination": terms["destinations"][gir.fallback.destination_id],
        "route": route_literal,
        "effective": iso_z(gir.effective_time),
        "expiry": iso_z(gir.expiry_time),
        "protection": terms["protection_template"],
    }


def render_clauses(gir: GIR, language: Language, channel: str) -> dict[str, str]:
    terms = load_terminology()["languages"][language.value]
    literals = canonical_literals(gir, language)
    audience_action = terms["audience_template"].format(**literals)
    if channel == "pa":
        audience_action = audience_action.replace(
            literals["sections"], f"Attention — {literals['sections']}", 1
        )
    return {
        "audience_action": audience_action,
        "route_clause": terms["route_template"].format(**literals),
        "fallback_clause": terms["fallback_template"].format(**literals),
        "protection_clause": terms["protection_template"],
        "validity_clause": terms["validity_template"].format(**literals),
        "optional_explanation": terms["explanation"],
    }
