from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.domain.diagnostics import Diagnostic
from backend.app.domain.gir import GIR
from backend.app.domain.guidance import GuidanceVariant
from backend.app.domain.workflow import LifecycleState
from backend.app.persistence.models.run import (
    CompilerResultModel,
    DiagnosticModel,
    GenerationRun,
    GIRVersionModel,
    GuidanceVariantModel,
)
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import (
    SemanticComparisonModel,
)
from backend.app.services.golden_flow.common import (
    TransitionError,
    ValidationError,
    append_event,
    transition_run,
)
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.guidance import GuidanceService
from backend.app.services.guidance.reverse_compiler import reverse_compile_guidance
from backend.app.services.guidance.service import GuidanceGenerationResult
from backend.app.services.integrity import domain_hash


class GuidanceWorkflow:
    @staticmethod
    async def _current_gir(
        db: AsyncSession, run_id: UUID
    ) -> tuple[GIRVersionModel, GIR]:
        result = await db.execute(
            select(GIRVersionModel)
            .where(
                GIRVersionModel.run_id == run_id,
                GIRVersionModel.is_current.is_(True),
            )
            .order_by(GIRVersionModel.version.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValidationError("Current GIR is missing.")
        return model, GIR.model_validate(model.gir_data)

    @staticmethod
    async def _persist_compilation(
        db: AsyncSession,
        *,
        run: RunModel,
        generation: GenerationRun,
        variant_model: GuidanceVariantModel,
        variant: GuidanceVariant,
        gir: GIR,
        diagnostics: list[Diagnostic],
    ) -> None:
        meaning = reverse_compile_guidance(variant)
        compiler_hash = domain_hash("CROWDCUE_COMPILED_MEANING_V1", meaning)
        compiler = CompilerResultModel(
            variant_id=variant_model.id,
            compiled_meaning=meaning.model_dump(mode="json"),
            compiler_version=run.compiler_version,
            result_hash=compiler_hash,
        )
        db.add(compiler)
        await db.flush()
        variant_diagnostics = [
            item
            for item in diagnostics
            if item.language == variant.language.value
            and item.channel == variant.channel.value
        ]
        differences = [item.model_dump(mode="json") for item in variant_diagnostics]
        comparison_hash = domain_hash(
            "CROWDCUE_SEMANTIC_COMPARISON_V1",
            {"compiled": compiler_hash, "differences": differences},
        )
        db.add(
            SemanticComparisonModel(
                compiler_result_id=compiler.id,
                differences=differences,
                is_equivalent=not variant_diagnostics,
                result_hash=comparison_hash,
            )
        )
        for item in variant_diagnostics:
            db.add(
                DiagnosticModel(
                    generation_run_id=generation.id,
                    variant_id=variant_model.id,
                    stage=item.stage.value,
                    severity=item.severity.value,
                    code=item.code,
                    message=item.message,
                    details=jsonable_encoder(item.model_dump()),
                    blocking=item.blocking,
                )
            )

    @staticmethod
    def _validate_fault_injection(enable_fault_injection: bool) -> None:
        if enable_fault_injection and not settings.ENABLE_DEMO_FAULT_INJECTION:
            raise ValidationError(
                "Demo fault injection is disabled by server configuration."
            )

    @classmethod
    async def _begin_guidance_verification(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
    ) -> GIR:
        run, _ = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        current = transition_run(run, LifecycleState.GUIDANCE_VERIFYING)
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="GUIDANCE_VERIFICATION_STARTED",
            payload={"from_state": current.value, "to_state": run.lifecycle_state},
        )
        await db.commit()
        _, gir = await cls._current_gir(db, run_id)
        return gir

    @classmethod
    async def _restore_retryable_generation_state(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        error: Exception,
    ) -> None:
        run, _ = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.GUIDANCE_VERIFYING:
            return
        failed_from = transition_run(run, LifecycleState.CANDIDATE_SELECTED)
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="GUIDANCE_GENERATION_FAILED",
            payload={
                "from_state": failed_from.value,
                "to_state": LifecycleState.CANDIDATE_SELECTED.value,
                "safe_error_code": type(error).__name__,
                "retry_allowed": True,
            },
        )
        await db.commit()

    @classmethod
    async def _generate_with_recovery(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        gir: GIR,
        enable_fault_injection: bool,
        guidance_service: GuidanceService | None,
    ) -> tuple[GuidanceGenerationResult, datetime, datetime]:
        service = guidance_service or GuidanceService()
        started_at = datetime.now(timezone.utc)
        try:
            result = await service.generate_and_verify_guidance(
                gir, enable_fault_injection=enable_fault_injection
            )
        except Exception as exc:
            await cls._restore_retryable_generation_state(
                db,
                run_id=run_id,
                session_id=session_id,
                error=exc,
            )
            raise
        return result, started_at, datetime.now(timezone.utc)

    @staticmethod
    def _new_generation_record(
        *,
        run_id: UUID,
        result: GuidanceGenerationResult,
        started_at: datetime,
        completed_at: datetime,
    ) -> GenerationRun:
        provenance = result.provenance
        return GenerationRun(
            preflight_run_id=run_id,
            model_used=provenance.get("model") or settings.GEMINI_MODEL,
            provider=provenance["provider"],
            status="BLOCKED" if result.diagnostics else "PASSED",
            fallback_used=result.fallback_used,
            request_count=int(provenance.get("request_count", 0)),
            successful_request_count=int(provenance.get("successful_request_count", 0)),
            attempt_count=int(provenance.get("attempt_count", 0)),
            safe_error_code=provenance.get("safe_error_code"),
            request_id_hash=provenance.get("request_id_hash"),
            provenance=jsonable_encoder(provenance),
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=int(provenance.get("latency_ms", 0)),
        )

    @classmethod
    async def _persist_generated_variants(
        cls,
        db: AsyncSession,
        *,
        run: RunModel,
        generation: GenerationRun,
        gir: GIR,
        result: GuidanceGenerationResult,
    ) -> None:
        persisted: list[tuple[GuidanceVariantModel, GuidanceVariant]] = []
        for variant in result.variants:
            model = GuidanceVariantModel(
                generation_run_id=generation.id,
                language=variant.language.value,
                channel=variant.channel.value,
                version=variant.version,
                audience_action=variant.audience_action,
                route_clause=variant.route_clause,
                fallback_clause=variant.fallback_clause,
                protection_clause=variant.protection_clause,
                validity_clause=variant.validity_clause,
                optional_explanation=variant.optional_explanation,
                rendered_text=variant.rendered_text,
                content_hash=variant.content_hash,
                is_current=True,
            )
            db.add(model)
            await db.flush()
            persisted.append((model, variant))
        for model, variant in persisted:
            await cls._persist_compilation(
                db,
                run=run,
                generation=generation,
                variant_model=model,
                variant=variant,
                gir=gir,
                diagnostics=result.diagnostics,
            )

    @staticmethod
    def _semantic_target(result: GuidanceGenerationResult) -> LifecycleState:
        if any(item.blocking for item in result.diagnostics):
            return LifecycleState.PREFLIGHT_BLOCKED
        return LifecycleState.SEMANTIC_PASSED

    @classmethod
    async def _complete_guidance_verification(
        cls,
        db: AsyncSession,
        *,
        run: RunModel,
        run_id: UUID,
        session_id: UUID,
        result: GuidanceGenerationResult,
    ) -> None:
        target = cls._semantic_target(result)
        from_state = transition_run(run, target)
        if result.provenance.get("fault_injection"):
            await append_event(
                db,
                session_id=session_id,
                run_id=run_id,
                event_type="DEMO_FAULT_INJECTED",
                payload={"fault_code": result.provenance.get("fault_code")},
            )
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type=(
                "SEMANTIC_BLOCKED" if result.diagnostics else "SEMANTIC_PASSED"
            ),
            payload={
                "from_state": from_state.value,
                "to_state": target.value,
                "diagnostic_codes": [item.code for item in result.diagnostics],
                "provenance": result.provenance,
            },
        )
        await db.commit()

    @classmethod
    async def generate_guidance(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        enable_fault_injection: bool,
        guidance_service: GuidanceService | None = None,
    ) -> dict[str, Any]:
        cls._validate_fault_injection(enable_fault_injection)
        gir = await cls._begin_guidance_verification(
            db, run_id=run_id, session_id=session_id
        )
        result, started_at, completed_at = await cls._generate_with_recovery(
            db,
            run_id=run_id,
            session_id=session_id,
            gir=gir,
            enable_fault_injection=enable_fault_injection,
            guidance_service=guidance_service,
        )
        run, _ = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.GUIDANCE_VERIFYING:
            raise TransitionError("Run changed while guidance was generated.")
        generation = cls._new_generation_record(
            run_id=run_id,
            result=result,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(generation)
        await db.flush()
        await cls._persist_generated_variants(
            db,
            run=run,
            generation=generation,
            gir=gir,
            result=result,
        )
        await cls._complete_guidance_verification(
            db,
            run=run,
            run_id=run_id,
            session_id=session_id,
            result=result,
        )
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "variants": [item.model_dump(mode="json") for item in result.variants],
            "diagnostics": [
                item.model_dump(mode="json") for item in result.diagnostics
            ],
            "provenance": result.provenance,
        }
