from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.workflow import LifecycleState, validate_transition
from backend.app.persistence.models.run import (
    ApprovalRecordModel,
    CompilerResultModel,
    DiagnosticModel,
    GenerationRun,
    GuidanceVariantModel,
)
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import (
    SemanticComparisonModel,
    SimulationRunModel,
)
from backend.app.persistence.models.run import VenueStateSnapshot as SnapshotModel
from backend.app.services.golden_flow.common import (
    TransitionError,
    ValidationError,
    append_event,
    transition_run,
)
from backend.app.services.golden_flow.guidance_workflow import GuidanceWorkflow
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.integrity import domain_hash


class ApprovalWorkflow:
    @staticmethod
    async def _latest_generation_evidence(
        db: AsyncSession, run_id: UUID
    ) -> GenerationRun:
        result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        generation = result.scalar_one_or_none()
        if generation is None:
            raise ValidationError("Generation evidence is missing.")
        return generation

    @staticmethod
    async def _approval_variants(
        db: AsyncSession, generation_id: UUID
    ) -> list[GuidanceVariantModel]:
        result = await db.execute(
            select(GuidanceVariantModel)
            .where(
                GuidanceVariantModel.generation_run_id == generation_id,
                GuidanceVariantModel.is_current.is_(True),
            )
            .order_by(
                GuidanceVariantModel.language,
                GuidanceVariantModel.channel,
            )
        )
        variants = list(result.scalars().all())
        if len(variants) != 6:
            raise ValidationError("Exactly six current public variants are required.")
        return variants

    @staticmethod
    async def _semantic_item(
        db: AsyncSession, variant: GuidanceVariantModel
    ) -> dict[str, str]:
        compiled_result = await db.execute(
            select(CompilerResultModel)
            .where(CompilerResultModel.variant_id == variant.id)
            .order_by(CompilerResultModel.id.desc())
            .limit(1)
        )
        compiled = compiled_result.scalar_one_or_none()
        if compiled is None:
            raise ValidationError("Compiler evidence is missing.")
        comparison_result = await db.execute(
            select(SemanticComparisonModel)
            .where(SemanticComparisonModel.compiler_result_id == compiled.id)
            .order_by(SemanticComparisonModel.id.desc())
            .limit(1)
        )
        comparison = comparison_result.scalar_one_or_none()
        if comparison is None or not comparison.is_equivalent:
            raise ValidationError("Current semantic evidence is not equivalent.")
        return {
            "language": variant.language,
            "channel": variant.channel,
            "variant_id": str(variant.id),
            "result_hash": comparison.result_hash,
        }

    @classmethod
    async def _semantic_items(
        cls,
        db: AsyncSession,
        variants: list[GuidanceVariantModel],
    ) -> list[dict[str, str]]:
        return [await cls._semantic_item(db, variant) for variant in variants]

    @staticmethod
    async def _approval_diagnostics(
        db: AsyncSession, generation_id: UUID
    ) -> list[DiagnosticModel]:
        result = await db.execute(
            select(DiagnosticModel).where(
                DiagnosticModel.generation_run_id == generation_id
            )
        )
        diagnostics = list(result.scalars().all())
        if any(item.blocking for item in diagnostics):
            raise ValidationError("Unresolved blocking diagnostics prevent approval.")
        return diagnostics

    @staticmethod
    async def _passing_simulation(
        db: AsyncSession, candidate_id: UUID | None
    ) -> SimulationRunModel:
        result = await db.execute(
            select(SimulationRunModel)
            .where(SimulationRunModel.candidate_id == candidate_id)
            .order_by(SimulationRunModel.created_at.desc())
            .limit(1)
        )
        simulation = result.scalar_one_or_none()
        if simulation is None or simulation.verdict == "BLOCK":
            raise ValidationError("Passing simulation evidence is missing.")
        return simulation

    @staticmethod
    def _variant_hashes(
        variants: list[GuidanceVariantModel],
    ) -> list[dict[str, Any]]:
        return sorted(
            [
                {
                    "language": variant.language,
                    "channel": variant.channel,
                    "version": variant.version,
                    "hash": variant.content_hash,
                }
                for variant in variants
            ],
            key=lambda item: (item["language"], item["channel"]),
        )

    @staticmethod
    def _diagnostic_items(
        diagnostics: list[DiagnosticModel],
    ) -> list[dict[str, Any]]:
        return sorted(
            [
                {
                    "code": item.code,
                    "blocking": item.blocking,
                    "resolved": item.resolved_at is not None,
                    "variant_id": str(item.variant_id) if item.variant_id else None,
                }
                for item in diagnostics
            ],
            key=lambda item: (
                item["code"],
                item["variant_id"] or "",
                item["blocking"],
                item["resolved"],
            ),
        )

    @classmethod
    async def _bundle_payload(
        cls,
        db: AsyncSession,
        run: RunModel,
        snapshot: SnapshotModel,
        *,
        run_version_override: int | None = None,
    ) -> dict[str, Any]:
        gir_model, _ = await GuidanceWorkflow._current_gir(db, run.id)
        generation = await cls._latest_generation_evidence(db, run.id)
        variants = await cls._approval_variants(db, generation.id)
        semantic_items = await cls._semantic_items(db, variants)
        diagnostics = await cls._approval_diagnostics(db, generation.id)
        simulation = await cls._passing_simulation(db, run.selected_candidate_id)
        return {
            "hash_contract_version": "CROWDCUE_APPROVAL_BUNDLE_V1",
            "run_id": str(run.id),
            "run_version": (
                run.version_id if run_version_override is None else run_version_override
            ),
            "candidate_id": str(run.selected_candidate_id),
            "gir_hash": gir_model.content_hash,
            "snapshot_hash": snapshot.canonical_input_hash,
            "variant_hashes": cls._variant_hashes(variants),
            "semantic_result_hash": domain_hash(
                "CROWDCUE_SEMANTIC_SET_V1",
                sorted(
                    semantic_items,
                    key=lambda item: (item["language"], item["channel"]),
                ),
            ),
            "diagnostic_set_hash": domain_hash(
                "CROWDCUE_DIAGNOSTIC_SET_V1",
                cls._diagnostic_items(diagnostics),
            ),
            "simulation_result_hash": simulation.result_hash,
            "reference_data_version": run.reference_data_version,
            "terminology_version": run.terminology_version,
            "compiler_version": run.compiler_version,
            "simulation_policy_version": run.simulation_policy_version,
        }

    @classmethod
    async def expected_bundle_hash(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> str | None:
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.PREFLIGHT_PASSED:
            return None
        payload = await cls._bundle_payload(db, run, snapshot)
        return domain_hash("CROWDCUE_APPROVAL_BUNDLE_V1", payload)

    @classmethod
    async def approve(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        approved_by_user_id: UUID,
        approver_role: str,
        approval_note: str | None,
        expected_bundle_hash: str,
    ) -> dict[str, Any]:
        normalized_role = approver_role.strip().upper()
        if normalized_role not in {"OPERATOR", "SUPERVISOR", "ADMINISTRATOR"}:
            raise ValidationError("Approver role is not permitted.")
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        current = LifecycleState(run.lifecycle_state)
        if not validate_transition(current, LifecycleState.APPROVED):
            raise TransitionError("Run is not eligible for approval.")
        payload = await cls._bundle_payload(db, run, snapshot)
        server_hash = domain_hash("CROWDCUE_APPROVAL_BUNDLE_V1", payload)
        if expected_bundle_hash != server_hash:
            raise TransitionError("Approval bundle hash is stale or invalid.")
        approval = ApprovalRecordModel(
            run_id=run.id,
            approved_by_user_id=approved_by_user_id,
            approver_role=normalized_role,
            run_version=run.version_id,
            bundle_hash=server_hash,
            notes=approval_note,
        )
        db.add(approval)
        run.decision_bundle_hash = server_hash
        transition_run(run, LifecycleState.APPROVED)
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="APPROVAL_RECORDED",
            payload={
                "from_state": current.value,
                "to_state": LifecycleState.APPROVED.value,
                "approved_by_user_id": str(approved_by_user_id),
                "approver_role": normalized_role,
                "decision_bundle_hash": server_hash,
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "decision_bundle_hash": server_hash,
            "approved_at": approval.approved_at.isoformat(),
        }
