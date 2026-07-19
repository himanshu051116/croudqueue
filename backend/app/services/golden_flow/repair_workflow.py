from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.diagnostics import Diagnostic
from backend.app.domain.gir import GIR
from backend.app.domain.guidance import GuidanceChannel, GuidanceVariant, Language
from backend.app.domain.workflow import LifecycleState
from backend.app.persistence.models.run import (
    DiagnosticModel,
    GenerationRun,
    GuidanceVariantModel,
)
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import (
    RepairAttemptModel,
)
from backend.app.services.golden_flow.common import (
    ValidationError,
    append_event,
    transition_run,
)
from backend.app.services.golden_flow.guidance_workflow import GuidanceWorkflow
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.guidance import GuidanceService


class RepairWorkflow:
    @staticmethod
    async def _latest_generation(db: AsyncSession, run_id: UUID) -> GenerationRun:
        result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        generation = result.scalar_one_or_none()
        if generation is None:
            raise ValidationError("No guidance generation exists.")
        return generation

    @staticmethod
    async def _current_variant_models(
        db: AsyncSession, generation_id: UUID
    ) -> list[GuidanceVariantModel]:
        result = await db.execute(
            select(GuidanceVariantModel).where(
                GuidanceVariantModel.generation_run_id == generation_id,
                GuidanceVariantModel.is_current.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _to_domain_variant(model: GuidanceVariantModel) -> GuidanceVariant:
        return GuidanceVariant(
            language=Language(model.language),
            channel=GuidanceChannel(model.channel),
            version=model.version,
            audience_action=model.audience_action,
            route_clause=model.route_clause,
            fallback_clause=model.fallback_clause,
            protection_clause=model.protection_clause,
            validity_clause=model.validity_clause,
            optional_explanation=model.optional_explanation,
            rendered_text=model.rendered_text,
            content_hash=model.content_hash,
        )

    @classmethod
    def _to_domain_variants(
        cls, models: list[GuidanceVariantModel]
    ) -> list[GuidanceVariant]:
        return [cls._to_domain_variant(model) for model in models]

    @staticmethod
    def _spanish_fan_app_model(
        models: list[GuidanceVariantModel],
    ) -> GuidanceVariantModel:
        try:
            return next(
                model
                for model in models
                if model.language == "es" and model.channel == "fan_app"
            )
        except StopIteration as exc:
            raise ValidationError("Spanish Fan App variant is missing.") from exc

    @staticmethod
    def _spanish_fan_app_variant(
        variants: list[GuidanceVariant],
    ) -> GuidanceVariant:
        try:
            return next(
                item
                for item in variants
                if item.language is Language.ES
                and item.channel is GuidanceChannel.FAN_APP
            )
        except StopIteration as exc:
            raise ValidationError(
                "Repaired Spanish Fan App variant is missing."
            ) from exc

    @staticmethod
    async def _blocking_repair_diagnostic(
        db: AsyncSession, generation_id: UUID
    ) -> DiagnosticModel:
        result = await db.execute(
            select(DiagnosticModel)
            .where(
                DiagnosticModel.generation_run_id == generation_id,
                DiagnosticModel.blocking.is_(True),
                DiagnosticModel.code == "PROTECTED_COHORT_OMITTED",
            )
            .order_by(DiagnosticModel.id)
        )
        diagnostic = result.scalars().first()
        if diagnostic is None:
            raise ValidationError("Repair target diagnostic is missing.")
        return diagnostic

    @staticmethod
    def _new_repaired_model(
        generation_id: UUID, repaired: GuidanceVariant
    ) -> GuidanceVariantModel:
        return GuidanceVariantModel(
            generation_run_id=generation_id,
            language=repaired.language.value,
            channel=repaired.channel.value,
            version=repaired.version,
            audience_action=repaired.audience_action,
            route_clause=repaired.route_clause,
            fallback_clause=repaired.fallback_clause,
            protection_clause=repaired.protection_clause,
            validity_clause=repaired.validity_clause,
            optional_explanation=repaired.optional_explanation,
            rendered_text=repaired.rendered_text,
            content_hash=repaired.content_hash,
            is_current=True,
        )

    @staticmethod
    def _unaffected_variant_hashes(
        models: list[GuidanceVariantModel], target_id: UUID
    ) -> dict[str, str]:
        return {
            f"{model.language}:{model.channel}": model.content_hash
            for model in models
            if model.id != target_id
        }

    @staticmethod
    def _spanish_clauses_unchanged(
        original: GuidanceVariantModel, repaired: GuidanceVariant
    ) -> bool:
        return all(
            (
                original.audience_action == repaired.audience_action,
                original.route_clause == repaired.route_clause,
                original.fallback_clause == repaired.fallback_clause,
                original.validity_clause == repaired.validity_clause,
                (original.optional_explanation or "")
                == (repaired.optional_explanation or ""),
            )
        )

    @classmethod
    async def _persist_repaired_variant(
        cls,
        db: AsyncSession,
        *,
        run: RunModel,
        generation: GenerationRun,
        original: GuidanceVariantModel,
        repaired: GuidanceVariant,
        diagnostic: DiagnosticModel,
        gir: GIR,
        diagnostics: list[Diagnostic],
    ) -> GuidanceVariantModel:
        original.is_current = False
        new_model = cls._new_repaired_model(generation.id, repaired)
        db.add(new_model)
        await db.flush()
        db.add(
            RepairAttemptModel(
                variant_id=original.id,
                diagnostic_id=diagnostic.id,
                target_clause="protection_clause",
                original_text=original.protection_clause,
                repaired_text=repaired.protection_clause,
                generation_run_id=generation.id,
                succeeded=not diagnostics,
            )
        )
        diagnostic.blocking = False
        diagnostic.resolved_at = datetime.now(timezone.utc)
        await GuidanceWorkflow._persist_compilation(
            db,
            run=run,
            generation=generation,
            variant_model=new_model,
            variant=repaired,
            gir=gir,
            diagnostics=diagnostics,
        )
        return new_model

    @staticmethod
    def _apply_repair_outcome(run: RunModel, diagnostics: list[Diagnostic]) -> None:
        if diagnostics:
            run.lifecycle_state = LifecycleState.PREFLIGHT_BLOCKED.value
            return
        transition_run(run, LifecycleState.SEMANTIC_PASSED)

    @classmethod
    async def repair(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, _ = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        current = transition_run(run, LifecycleState.GUIDANCE_VERIFYING)
        generation = await cls._latest_generation(db, run_id)
        models = await cls._current_variant_models(db, generation.id)
        _, gir = await GuidanceWorkflow._current_gir(db, run_id)
        repaired_variants, diagnostics = GuidanceService.repair_variant(
            cls._to_domain_variants(models), gir
        )
        original = cls._spanish_fan_app_model(models)
        repaired = cls._spanish_fan_app_variant(repaired_variants)
        blocking_diagnostic = await cls._blocking_repair_diagnostic(db, generation.id)
        new_model = await cls._persist_repaired_variant(
            db,
            run=run,
            generation=generation,
            original=original,
            repaired=repaired,
            diagnostic=blocking_diagnostic,
            gir=gir,
            diagnostics=diagnostics,
        )
        cls._apply_repair_outcome(run, diagnostics)
        unchanged_hashes = cls._unaffected_variant_hashes(models, original.id)
        unchanged_spanish_clauses = cls._spanish_clauses_unchanged(original, repaired)
        if not unchanged_spanish_clauses:
            raise ValidationError("Targeted repair changed an unrelated clause.")
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="TARGETED_REPAIR_COMPLETED",
            payload={
                "from_state": current.value,
                "to_state": run.lifecycle_state,
                "original_variant_id": str(original.id),
                "repaired_variant_id": str(new_model.id),
                "target_clause": "protection_clause",
                "unaffected_variant_hashes": unchanged_hashes,
                "unaffected_spanish_clauses_unchanged": unchanged_spanish_clauses,
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "repaired_variant": repaired.model_dump(mode="json"),
            "original_variant_id": original.id,
            "repaired_variant_id": new_model.id,
            "unaffected_variant_hashes": unchanged_hashes,
            "unaffected_spanish_clauses_unchanged": unchanged_spanish_clauses,
            "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
        }
