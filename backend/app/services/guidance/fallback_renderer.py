from __future__ import annotations

from backend.app.domain.gir import GIR
from backend.app.domain.guidance import GuidanceChannel, GuidanceVariant, Language
from backend.app.services.guidance.terminology import render_clauses
from backend.app.services.integrity import content_hash


def build_variant(
    gir: GIR,
    language: Language,
    channel: GuidanceChannel,
    clauses: dict[str, str],
    *,
    version: int = 1,
) -> GuidanceVariant:
    ordered = [
        clauses["audience_action"],
        clauses["route_clause"],
        clauses["fallback_clause"],
        clauses["protection_clause"],
        clauses["validity_clause"],
    ]
    optional = clauses.get("optional_explanation")
    if optional:
        ordered.append(optional)
    rendered = "\n".join(ordered)
    return GuidanceVariant(
        language=language,
        channel=channel,
        version=version,
        audience_action=clauses["audience_action"],
        route_clause=clauses["route_clause"],
        fallback_clause=clauses["fallback_clause"],
        protection_clause=clauses["protection_clause"],
        validity_clause=clauses["validity_clause"],
        optional_explanation=optional,
        rendered_text=rendered,
        content_hash=content_hash(rendered),
    )


def render_fallback_guidance(gir: GIR) -> list[GuidanceVariant]:
    variants: list[GuidanceVariant] = []
    for language in Language:
        for channel in GuidanceChannel:
            clauses = render_clauses(gir, language, channel.value)
            variants.append(build_variant(gir, language, channel, clauses))
    return variants
