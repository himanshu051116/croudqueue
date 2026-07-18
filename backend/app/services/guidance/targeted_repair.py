from __future__ import annotations

from backend.app.domain.gir import GIR
from backend.app.domain.guidance import GuidanceChannel, GuidanceVariant, Language
from backend.app.services.guidance.fallback_renderer import build_variant
from backend.app.services.guidance.terminology import render_clauses


def repair_spanish_protection_clause(
    variant: GuidanceVariant, gir: GIR
) -> GuidanceVariant:
    if (
        variant.language is not Language.ES
        or variant.channel is not GuidanceChannel.FAN_APP
    ):
        raise ValueError("Targeted repair only supports the Spanish Fan App variant.")
    canonical = render_clauses(gir, Language.ES, GuidanceChannel.FAN_APP.value)
    clauses = {
        "audience_action": variant.audience_action,
        "route_clause": variant.route_clause,
        "fallback_clause": variant.fallback_clause,
        "protection_clause": canonical["protection_clause"],
        "validity_clause": variant.validity_clause,
        "optional_explanation": variant.optional_explanation or "",
    }
    return build_variant(
        gir,
        variant.language,
        variant.channel,
        clauses,
        version=variant.version + 1,
    )
