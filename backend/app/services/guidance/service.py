from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from backend.app.config import settings
from backend.app.domain.diagnostics import Diagnostic
from backend.app.domain.gir import GIR
from backend.app.domain.guidance import GuidanceChannel, GuidanceVariant, Language
from backend.app.services.guidance.fallback_renderer import (
    build_variant,
    render_fallback_guidance,
)
from backend.app.services.guidance.gemini_client import GeminiClient, GeminiError
from backend.app.services.guidance.reverse_compiler import reverse_compile_guidance
from backend.app.services.guidance.semantic_analyser import analyze_semantic_equivalence
from backend.app.services.guidance.targeted_repair import (
    repair_spanish_protection_clause,
)
from backend.app.services.guidance.terminology import canonical_literals
from backend.app.services.integrity import domain_hash


class ClausePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience_action: str
    route_clause: str
    fallback_clause: str
    protection_clause: str
    validity_clause: str
    optional_explanation: str | None = None


class LanguagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fan_app: ClausePayload
    pa: ClausePayload


class MultilingualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    en: LanguagePayload
    es: LanguagePayload
    fr: LanguagePayload


@dataclass(frozen=True)
class GuidanceGenerationResult:
    variants: list[GuidanceVariant]
    diagnostics: list[Diagnostic]
    fallback_used: bool
    provenance: dict[str, Any]


class GuidanceService:
    def __init__(self, client: GeminiClient | None = None) -> None:
        self.client = client or GeminiClient()

    @staticmethod
    def response_schema() -> dict[str, Any]:
        clause = {
            "type": "object",
            "properties": {
                "audience_action": {"type": "string"},
                "route_clause": {"type": "string"},
                "fallback_clause": {"type": "string"},
                "protection_clause": {"type": "string"},
                "validity_clause": {"type": "string"},
                "optional_explanation": {"type": "string"},
            },
            "required": [
                "audience_action",
                "route_clause",
                "fallback_clause",
                "protection_clause",
                "validity_clause",
                "optional_explanation",
            ],
            "additionalProperties": False,
        }
        language = {
            "type": "object",
            "properties": {"fan_app": clause, "pa": clause},
            "required": ["fan_app", "pa"],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {"en": language, "es": language, "fr": language},
            "required": ["en", "es", "fr"],
            "additionalProperties": False,
        }

    @staticmethod
    def build_prompt(gir: GIR) -> str:
        requirements = {
            language.value: canonical_literals(gir, language) for language in Language
        }
        return (
            "Render six stadium guidance variants. Return JSON only. "
            "Every field must preserve the authoritative GIR. Copy every supplied "
            "controlled literal verbatim into its assigned clause. Do not introduce "
            "new destinations, closures, waiting instructions, numbers, or cohorts. "
            "Use only restrained connective language.\n\n"
            f"GIR={gir.model_dump_json()}\n"
            f"CONTROLLED_LITERALS={requirements}"
        )

    @staticmethod
    def _payload_to_variants(
        gir: GIR, payload: MultilingualPayload
    ) -> list[GuidanceVariant]:
        variants: list[GuidanceVariant] = []
        for language in Language:
            language_payload = getattr(payload, language.value)
            for channel in GuidanceChannel:
                clauses = getattr(language_payload, channel.value).model_dump()
                variants.append(build_variant(gir, language, channel, clauses))
        return variants

    @staticmethod
    def verify(gir: GIR, variants: list[GuidanceVariant]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for variant in variants:
            meaning = reverse_compile_guidance(variant)
            diagnostics.extend(analyze_semantic_equivalence(gir, meaning, variant))
        return diagnostics

    async def generate_and_verify_guidance(
        self,
        gir: GIR,
        *,
        enable_fault_injection: bool = False,
    ) -> GuidanceGenerationResult:
        fallback_used = False
        provenance: dict[str, Any] = {
            "provider": "deterministic",
            "model": None,
            "request_count": 0,
            "successful_request_count": 0,
            "attempt_count": 0,
            "latency_ms": 0,
            "safe_error_code": None,
            "request_id_hash": None,
            "fault_injection": False,
        }
        variants: list[GuidanceVariant]
        response = None
        try:
            response = await self.client.generate(
                prompt=self.build_prompt(gir), schema=self.response_schema()
            )
            payload = MultilingualPayload.model_validate(response.payload)
            live_variants = self._payload_to_variants(gir, payload)
            live_diagnostics = self.verify(gir, live_variants)
            if any(item.blocking for item in live_diagnostics):
                raise GeminiError(
                    "SEMANTIC_VALIDATION_FAILED",
                    "Gemini output failed deterministic semantic validation.",
                    attempt_count=response.attempt_count,
                )
            variants = live_variants
            provenance.update(
                provider="gemini",
                model=settings.GEMINI_MODEL,
                request_count=1,
                successful_request_count=1,
                attempt_count=response.attempt_count,
                latency_ms=response.latency_ms,
                request_id_hash=(
                    domain_hash("CROWDCUE_GEMINI_REQUEST_ID_V1", response.request_id)
                    if response.request_id
                    else None
                ),
            )
        except (GeminiError, ValidationError, ValueError) as exc:
            fallback_used = True
            variants = render_fallback_guidance(gir)
            provenance.update(
                provider="deterministic_fallback",
                model=settings.GEMINI_MODEL,
                request_count=1 if settings.gemini_configured else 0,
                successful_request_count=1 if response is not None else 0,
                attempt_count=(
                    response.attempt_count
                    if response is not None
                    else int(getattr(exc, "attempt_count", 0))
                ),
                latency_ms=response.latency_ms if response is not None else 0,
                safe_error_code=getattr(exc, "code", exc.__class__.__name__),
            )

        baseline_diagnostics = self.verify(gir, variants)
        if baseline_diagnostics:
            provenance["safe_error_code"] = "SYSTEM_CONFIGURATION_ERROR"
            return GuidanceGenerationResult(
                variants=variants,
                diagnostics=baseline_diagnostics,
                fallback_used=fallback_used,
                provenance=provenance,
            )

        if enable_fault_injection:
            if not settings.ENABLE_DEMO_FAULT_INJECTION:
                raise ValueError("Demo fault injection is disabled by configuration.")
            updated: list[GuidanceVariant] = []
            for variant in variants:
                if (
                    variant.language is Language.ES
                    and variant.channel is GuidanceChannel.FAN_APP
                ):
                    clauses = variant.model_dump()
                    clauses["protection_clause"] = ""
                    clauses.pop("rendered_text")
                    clauses.pop("content_hash")
                    updated.append(
                        build_variant(
                            gir,
                            variant.language,
                            variant.channel,
                            clauses,
                            version=variant.version,
                        )
                    )
                else:
                    updated.append(variant)
            variants = updated
            provenance["fault_injection"] = True
            provenance["fault_code"] = "DEMO_ES_FAN_APP_PROTECTION_OMISSION"

        return GuidanceGenerationResult(
            variants=variants,
            diagnostics=self.verify(gir, variants),
            fallback_used=fallback_used,
            provenance=provenance,
        )

    @staticmethod
    def repair_variant(
        variants: list[GuidanceVariant], gir: GIR
    ) -> tuple[list[GuidanceVariant], list[Diagnostic]]:
        repaired: list[GuidanceVariant] = []
        found = False
        for variant in variants:
            if (
                variant.language is Language.ES
                and variant.channel is GuidanceChannel.FAN_APP
            ):
                repaired.append(repair_spanish_protection_clause(variant, gir))
                found = True
            else:
                repaired.append(variant)
        if not found:
            raise ValueError("Spanish Fan App variant is missing.")
        return repaired, GuidanceService.verify(gir, repaired)
