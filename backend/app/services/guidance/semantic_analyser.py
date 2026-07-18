from __future__ import annotations

from typing import Any

from backend.app.domain.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    DiagnosticStage,
)
from backend.app.domain.gir import GIR
from backend.app.domain.guidance import CompiledMeaning, GuidanceVariant


def _diagnostic(
    variant: GuidanceVariant,
    code: str,
    message: str,
    clause: str,
    expected: Any,
    actual: Any,
) -> Diagnostic:
    return Diagnostic(
        severity=DiagnosticSeverity.BLOCK,
        stage=DiagnosticStage.SEMANTIC_EQUIVALENCE,
        code=code,
        message=message,
        language=variant.language.value,
        channel=variant.channel.value,
        clause=clause,
        expected=expected,
        actual=actual,
        blocking=True,
    )


def analyze_semantic_equivalence(
    gir: GIR,
    meaning: CompiledMeaning,
    variant: GuidanceVariant,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    checks = [
        (
            meaning.audience_sections,
            gir.audience.sections,
            "AUDIENCE_SCOPE_MISMATCH",
            "audience_action",
        ),
        (
            meaning.approach_zones,
            gir.audience.approach_zones,
            "APPROACH_ZONE_MISMATCH",
            "audience_action",
        ),
        (
            meaning.action,
            gir.directive.action.value,
            "ACTION_DRIFT",
            "audience_action",
        ),
        (
            meaning.directive_strength,
            gir.directive.strength.value,
            "DIRECTIVE_STRENGTH_DRIFT",
            "audience_action",
        ),
        (
            meaning.destination_id,
            gir.destination_id,
            "DESTINATION_DRIFT",
            "audience_action",
        ),
        (meaning.route, gir.route, "ROUTE_DRIFT", "route_clause"),
        (
            meaning.fallback_action,
            gir.fallback.action.value,
            "FALLBACK_ACTION_MISMATCH",
            "fallback_clause",
        ),
        (
            meaning.fallback_destination_id,
            gir.fallback.destination_id,
            "FALLBACK_DESTINATION_MISMATCH",
            "fallback_clause",
        ),
        (
            meaning.effective_time,
            gir.effective_time,
            "VALIDITY_EFFECTIVE_MISMATCH",
            "validity_clause",
        ),
        (
            meaning.expiry_time,
            gir.expiry_time,
            "VALIDITY_EXPIRY_MISMATCH",
            "validity_clause",
        ),
    ]
    for actual, expected, code, clause in checks:
        if actual != expected:
            diagnostics.append(
                _diagnostic(
                    variant,
                    code,
                    f"{clause.replace('_', ' ').title()} does not preserve the GIR.",
                    clause,
                    expected,
                    actual,
                )
            )

    missing = set(gir.excluded_cohorts) - set(meaning.excluded_cohorts)
    if "mobility-assistance-cohort" in missing:
        diagnostics.append(
            _diagnostic(
                variant,
                "PROTECTED_COHORT_OMITTED",
                "Required protection for mobility-assistance guests is missing.",
                "protection_clause",
                sorted(gir.excluded_cohorts),
                sorted(meaning.excluded_cohorts),
            )
        )
    elif missing:
        diagnostics.append(
            _diagnostic(
                variant,
                "EXCLUDED_COHORT_OMITTED",
                "One or more excluded cohorts are missing.",
                "protection_clause",
                sorted(gir.excluded_cohorts),
                sorted(meaning.excluded_cohorts),
            )
        )

    allowed_destinations = {gir.destination_id}
    if gir.fallback.destination_id:
        allowed_destinations.add(gir.fallback.destination_id)
    additions = set(meaning.all_mentioned_destinations) - allowed_destinations
    if additions:
        diagnostics.append(
            _diagnostic(
                variant,
                "UNAUTHORIZED_DESTINATION_ADDED",
                "Rendered guidance introduces an unauthorized destination.",
                "rendered_text",
                sorted(allowed_destinations),
                sorted(additions),
            )
        )
    if meaning.closure_claims:
        diagnostics.append(
            _diagnostic(
                variant,
                "UNAUTHORIZED_CLOSURE_CLAIM",
                "Rendered guidance introduces an unauthorized closure claim.",
                "rendered_text",
                [],
                list(meaning.closure_claims),
            )
        )
    if meaning.waiting_claims:
        diagnostics.append(
            _diagnostic(
                variant,
                "UNAUTHORIZED_WAITING_INSTRUCTION",
                "Rendered guidance introduces an unauthorized waiting instruction.",
                "rendered_text",
                [],
                list(meaning.waiting_claims),
            )
        )
    if meaning.unsupported_numeric_claims:
        diagnostics.append(
            _diagnostic(
                variant,
                "UNSUPPORTED_NUMERIC_CLAIM",
                "Rendered guidance introduces an unsupported numeric claim.",
                "rendered_text",
                [],
                list(meaning.unsupported_numeric_claims),
            )
        )
    if meaning.negated_destinations:
        diagnostics.append(
            _diagnostic(
                variant,
                "NEGATION_INVERSION",
                "A destination was negated without GIR authority.",
                "rendered_text",
                [],
                list(meaning.negated_destinations),
            )
        )
    return diagnostics
