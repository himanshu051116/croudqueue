from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.audit import AuditEventModel
from backend.app.persistence.models.run import (
    ApprovalRecordModel,
)
from backend.app.persistence.models.run import (
    CandidateRejection as CandidateRejectionModel,
)
from backend.app.persistence.models.run import (
    DiagnosticModel,
    GenerationRun,
    GIRVersionModel,
    GuidanceVariantModel,
)
from backend.app.persistence.models.run import InterventionCandidate as CandidateModel
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import (
    PublicationBatchModel,
    PublicationDeliveryModel,
    SimulationRunModel,
)
from backend.app.persistence.models.run import VenueStateSnapshot as SnapshotModel
from backend.app.services.audit_service import AuditService
from backend.app.services.golden_flow.approval_workflow import ApprovalWorkflow
from backend.app.services.golden_flow.common import OwnershipError, RunNotFoundError
from backend.app.services.golden_flow.run_workflow import RunWorkflow


class ReadModel:
    @staticmethod
    async def _run_candidates(db: AsyncSession, run_id: UUID) -> list[CandidateModel]:
        result = await db.execute(
            select(CandidateModel).where(CandidateModel.run_id == run_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _rejections_by_candidate(
        db: AsyncSession, candidates: list[CandidateModel]
    ) -> dict[UUID, list[CandidateRejectionModel]]:
        candidate_ids = [item.id for item in candidates]
        if not candidate_ids:
            return {}
        result = await db.execute(
            select(CandidateRejectionModel).where(
                CandidateRejectionModel.candidate_id.in_(candidate_ids)
            )
        )
        grouped: dict[UUID, list[CandidateRejectionModel]] = {}
        for rejection in result.scalars().all():
            grouped.setdefault(rejection.candidate_id, []).append(rejection)
        return grouped

    @staticmethod
    async def _current_gir_model(
        db: AsyncSession, run_id: UUID
    ) -> GIRVersionModel | None:
        result = await db.execute(
            select(GIRVersionModel)
            .where(
                GIRVersionModel.run_id == run_id,
                GIRVersionModel.is_current.is_(True),
            )
            .order_by(GIRVersionModel.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _read_latest_generation(
        db: AsyncSession, run_id: UUID
    ) -> GenerationRun | None:
        result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _generation_details(
        db: AsyncSession, generation: GenerationRun | None
    ) -> tuple[list[GuidanceVariantModel], list[DiagnosticModel]]:
        if generation is None:
            return [], []
        variants_result = await db.execute(
            select(GuidanceVariantModel).where(
                GuidanceVariantModel.generation_run_id == generation.id,
                GuidanceVariantModel.is_current.is_(True),
            )
        )
        diagnostics_result = await db.execute(
            select(DiagnosticModel).where(
                DiagnosticModel.generation_run_id == generation.id
            )
        )
        return (
            list(variants_result.scalars().all()),
            list(diagnostics_result.scalars().all()),
        )

    @staticmethod
    async def _latest_simulation(
        db: AsyncSession, candidate_id: UUID | None
    ) -> SimulationRunModel | None:
        result = await db.execute(
            select(SimulationRunModel)
            .where(SimulationRunModel.candidate_id == candidate_id)
            .order_by(SimulationRunModel.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _approval_record(
        db: AsyncSession, run_id: UUID
    ) -> ApprovalRecordModel | None:
        result = await db.execute(
            select(ApprovalRecordModel).where(ApprovalRecordModel.run_id == run_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _latest_publication(
        db: AsyncSession, run_id: UUID
    ) -> tuple[PublicationBatchModel | None, list[PublicationDeliveryModel]]:
        result = await db.execute(
            select(PublicationBatchModel)
            .where(PublicationBatchModel.run_id == run_id)
            .order_by(PublicationBatchModel.started_at.desc())
            .limit(1)
        )
        batch = result.scalar_one_or_none()
        if batch is None:
            return None, []
        delivery_result = await db.execute(
            select(PublicationDeliveryModel)
            .where(PublicationDeliveryModel.batch_id == batch.id)
            .order_by(
                PublicationDeliveryModel.surface,
                PublicationDeliveryModel.language,
            )
        )
        return batch, list(delivery_result.scalars().all())

    @staticmethod
    def _serialize_rejection(item: CandidateRejectionModel) -> dict[str, Any]:
        return {
            "reason_code": item.reason_code,
            "message": item.message,
            "affected_route_id": item.affected_route_id,
            "affected_edge_key": item.affected_edge_key,
            "affected_asset_key": item.affected_asset_key,
        }

    @classmethod
    def _serialize_candidates(
        cls,
        candidates: list[CandidateModel],
        rejections: dict[UUID, list[CandidateRejectionModel]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "candidate_key": item.candidate_key,
                "title": item.title,
                "cohort_id": item.cohort_id,
                "destination_id": item.destination_id,
                "route_id": item.route_id,
                "is_viable": item.is_viable,
                "preliminary_rank": item.preliminary_rank,
                "selected": item.selected,
                "rejections": [
                    cls._serialize_rejection(rejection)
                    for rejection in rejections.get(item.id, [])
                ],
            }
            for item in candidates
        ]

    @staticmethod
    def _serialize_variants(
        variants: list[GuidanceVariantModel],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "language": item.language,
                "channel": item.channel,
                "version": item.version,
                "audience_action": item.audience_action,
                "route_clause": item.route_clause,
                "fallback_clause": item.fallback_clause,
                "protection_clause": item.protection_clause,
                "validity_clause": item.validity_clause,
                "optional_explanation": item.optional_explanation,
                "rendered_text": item.rendered_text,
                "content_hash": item.content_hash,
            }
            for item in variants
        ]

    @staticmethod
    def _serialize_diagnostics(
        diagnostics: list[DiagnosticModel],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "code": item.code,
                "stage": item.stage,
                "severity": item.severity,
                "message": item.message,
                "details": item.details,
                "blocking": item.blocking,
                "resolved_at": item.resolved_at,
            }
            for item in diagnostics
        ]

    @staticmethod
    def _serialize_approval(
        approval: ApprovalRecordModel | None,
    ) -> dict[str, Any] | None:
        if approval is None:
            return None
        return {
            "approved_by_user_id": approval.approved_by_user_id,
            "approver_role": approval.approver_role,
            "run_version": approval.run_version,
            "bundle_hash": approval.bundle_hash,
            "approval_note": approval.notes,
            "approved_at": approval.approved_at,
        }

    @staticmethod
    def _serialize_publication_batch(
        batch: PublicationBatchModel | None,
    ) -> dict[str, Any] | None:
        if batch is None:
            return None
        return {
            "id": batch.id,
            "status": batch.status,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at,
        }

    @staticmethod
    def _serialize_publication_deliveries(
        deliveries: list[PublicationDeliveryModel],
    ) -> list[dict[str, Any]]:
        return [
            {
                "surface": item.surface,
                "language": item.language,
                "status": item.status,
                "variant_id": item.variant_id,
                "error_message": item.error_message,
                "delivered_at": item.delivered_at,
            }
            for item in deliveries
        ]

    @classmethod
    async def details(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id)
        candidates = await cls._run_candidates(db, run_id)
        rejections = await cls._rejections_by_candidate(db, candidates)
        gir = await cls._current_gir_model(db, run_id)
        generation = await cls._read_latest_generation(db, run_id)
        variants, diagnostics = await cls._generation_details(db, generation)
        simulation = await cls._latest_simulation(db, run.selected_candidate_id)
        approval = await cls._approval_record(db, run_id)
        publication_batch, publication_deliveries = await cls._latest_publication(
            db, run_id
        )
        expected_hash = await ApprovalWorkflow.expected_bundle_hash(
            db, run_id=run_id, session_id=session_id
        )
        return cls._serialize_details(
            run=run,
            snapshot=snapshot,
            gir=gir,
            candidates=candidates,
            rejections=rejections,
            generation=generation,
            variants=variants,
            diagnostics=diagnostics,
            simulation=simulation,
            approval=approval,
            publication_batch=publication_batch,
            publication_deliveries=publication_deliveries,
            expected_hash=expected_hash,
        )

    @classmethod
    def _serialize_details(
        cls,
        *,
        run: RunModel,
        snapshot: SnapshotModel,
        gir: GIRVersionModel | None,
        candidates: list[CandidateModel],
        rejections: dict[UUID, list[CandidateRejectionModel]],
        generation: GenerationRun | None,
        variants: list[GuidanceVariantModel],
        diagnostics: list[DiagnosticModel],
        simulation: SimulationRunModel | None,
        approval: ApprovalRecordModel | None,
        publication_batch: PublicationBatchModel | None,
        publication_deliveries: list[PublicationDeliveryModel],
        expected_hash: str | None,
    ) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "session_id": snapshot.session_id,
            "scenario_key": snapshot.scenario_key,
            "lifecycle_state": run.lifecycle_state,
            "run_version": run.version_id,
            "selected_candidate_id": run.selected_candidate_id,
            "snapshot_hash": snapshot.canonical_input_hash,
            "gir": gir.gir_data if gir else None,
            "candidates": cls._serialize_candidates(candidates, rejections),
            "generation_provenance": generation.provenance if generation else None,
            "variants": cls._serialize_variants(variants),
            "diagnostics": cls._serialize_diagnostics(diagnostics),
            "simulation": simulation.metrics if simulation else None,
            "approval": cls._serialize_approval(approval),
            "publication_batch": cls._serialize_publication_batch(publication_batch),
            "publication_deliveries": cls._serialize_publication_deliveries(
                publication_deliveries
            ),
            "expected_bundle_hash": expected_hash,
            "decision_bundle_hash": run.decision_bundle_hash,
        }

    @staticmethod
    async def snapshot_details(
        db: AsyncSession, *, snapshot_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        snapshot = await db.get(SnapshotModel, snapshot_id)
        if snapshot is None:
            raise RunNotFoundError("Snapshot not found.")
        if snapshot.session_id != session_id:
            raise OwnershipError("Session does not own this snapshot.")
        return {
            "id": snapshot.id,
            "session_id": snapshot.session_id,
            "venue_id": snapshot.venue_id,
            "scenario_key": snapshot.scenario_key,
            "reference_data_version": snapshot.reference_data_version,
            "canonical_input_hash": snapshot.canonical_input_hash,
            "timestamp": snapshot.timestamp,
            "nodes_state": snapshot.nodes_state,
            "edges_state": snapshot.edges_state,
            "assets_state": snapshot.assets_state,
        }

    @classmethod
    async def audit_timeline(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        await RunWorkflow._owned_run(db, run_id, session_id)
        session_result = await db.execute(
            select(AuditEventModel)
            .where(AuditEventModel.session_id == session_id)
            .order_by(AuditEventModel.sequence_number)
        )
        session_events = list(session_result.scalars().all())
        events = [item for item in session_events if item.run_id == run_id]
        return {
            "run_id": run_id,
            "chain_scope": "session",
            "session_event_count": len(session_events),
            "chain_valid": AuditService.verify_chain(session_events),
            "events": [
                {
                    "id": item.id,
                    "sequence_number": item.sequence_number,
                    "event_type": item.event_type,
                    "payload": item.payload,
                    "created_at": item.created_at,
                    "previous_event_hash": item.previous_event_hash,
                    "event_hash": item.event_hash,
                }
                for item in events
            ],
        }
