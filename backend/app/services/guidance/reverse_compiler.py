from __future__ import annotations

import re
from datetime import datetime

from backend.app.domain.guidance import CompiledMeaning, GuidanceVariant
from backend.app.services.guidance.terminology import load_terminology

NODE_PATTERN = re.compile(r"node-[a-z0-9-]+")
ISO_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
SECTION_PATTERN = re.compile(r"(?:Sections|Secciones)\s+(\d{1,3})[–-](\d{1,3})")
PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%")
WAIT_PATTERNS = ("wait at", "espere en", "attendez à", "hold at")
CLOSURE_PATTERNS = (
    "is closed",
    "está cerrada",
    "est fermée",
    "gate closure",
)


def _expand_sections(match: re.Match[str] | None) -> tuple[str, ...]:
    if match is None:
        return ()
    start, end = int(match.group(1)), int(match.group(2))
    if end < start or end - start > 50:
        return ()
    return tuple(str(value) for value in range(start, end + 1))


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def reverse_compile_guidance(variant: GuidanceVariant) -> CompiledMeaning:
    terms = load_terminology()["languages"][variant.language.value]
    all_text = variant.rendered_text
    lower = all_text.lower()
    audience_lower = variant.audience_action.lower()
    fallback_lower = variant.fallback_clause.lower()

    sections = _expand_sections(SECTION_PATTERN.search(variant.audience_action))
    approach = tuple(
        key
        for key, literal in terms["approach"].items()
        if literal.lower() in audience_lower
    )

    action = next(
        (
            key
            for key, literal in terms["action"].items()
            if literal.lower() in audience_lower
        ),
        None,
    )
    strength_candidates = sorted(
        terms["strength"].items(), key=lambda item: len(item[1]), reverse=True
    )
    strength = next(
        (
            key
            for key, literal in strength_candidates
            if literal.lower() in audience_lower
        ),
        None,
    )

    destination = next(
        (
            key
            for key, literal in terms["destinations"].items()
            if literal.lower() in audience_lower
        ),
        None,
    )
    mentioned = tuple(
        sorted(
            {
                key
                for key, literal in terms["destinations"].items()
                if literal.lower() in lower
            }
        )
    )
    fallback_destination = next(
        (
            key
            for key, literal in terms["destinations"].items()
            if literal.lower() in fallback_lower
        ),
        None,
    )
    fallback_action = "REDIRECT" if fallback_destination else None

    route = tuple(NODE_PATTERN.findall(variant.route_clause))
    protection_literal = terms["protection_template"].lower()
    exclusions = (
        ("mobility-assistance-cohort",)
        if protection_literal in variant.protection_clause.lower()
        else ()
    )

    timestamps = ISO_PATTERN.findall(variant.validity_clause)
    effective = _parse_iso(timestamps[0]) if len(timestamps) >= 1 else None
    expiry = _parse_iso(timestamps[1]) if len(timestamps) >= 2 else None

    closure_claims = tuple(pattern for pattern in CLOSURE_PATTERNS if pattern in lower)
    waiting_claims = tuple(pattern for pattern in WAIT_PATTERNS if pattern in lower)
    unsupported_numbers = tuple(PERCENT_PATTERN.findall(all_text))
    negated_destinations = tuple(
        key
        for key, literal in terms["destinations"].items()
        if re.search(
            rf"(?:do not|no|ne pas).{{0,24}}{re.escape(literal.lower())}", lower
        )
    )

    return CompiledMeaning(
        audience_sections=sections,
        approach_zones=approach,
        action=action,
        directive_strength=strength,
        destination_id=destination,
        all_mentioned_destinations=mentioned,
        route=route,
        excluded_cohorts=exclusions,
        fallback_action=fallback_action,
        fallback_destination_id=fallback_destination,
        effective_time=effective,
        expiry_time=expiry,
        closure_claims=closure_claims,
        waiting_claims=waiting_claims,
        unsupported_numeric_claims=unsupported_numbers,
        negated_destinations=negated_destinations,
        raw_evidence={
            "audience_action": variant.audience_action,
            "route_clause": variant.route_clause,
            "fallback_clause": variant.fallback_clause,
            "protection_clause": variant.protection_clause,
            "validity_clause": variant.validity_clause,
        },
    )
