"""Pure serialization layer for read-model responses.

Transforms persistence models into API response dictionaries.
No database access, no transaction handling, no orchestration.
Deterministic output for deterministic input.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

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


class ReadSerializers:
    """Pure transformation functions for serializing run data to API responses."""

    @staticmethod
    def serialize_rejection(item: CandidateRejectionModel) -> dict[str, Any]:
        """Serialize a candidate rejection."""
        return {
            "reason_code": item.reason_code,
            "message": item.message,
            "affected_route_id": item.affected_route_id,
            "affected_edge_key": item.affected_edge_key,
            "affected_asset_key": item.affected_asset_key,
        }

    @classmethod
    def serialize_candidates(
        cls,
        candidates: list[CandidateModel],
        rejections: dict[UUID, list[CandidateRejectionModel]],
    ) -> list[dict[str, Any]]:
        """Serialize intervention candidates with their rejections."""
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
                    cls.serialize_rejection(rejection)
                    for rejection in rejections.get(item.id, [])
                ],
            }
            for item in candidates
        ]

    @staticmethod
    def serialize_variants(
        variants: list[GuidanceVariantModel],
    ) -> list[dict[str, Any]]:
        """Serialize guidance variants."""
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
    def serialize_diagnostics(
        diagnostics: list[DiagnosticModel],
    ) -> list[dict[str, Any]]:
        """Serialize generation diagnostics."""
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
    def serialize_approval(
        approval: ApprovalRecordModel | None,
    ) -> dict[str, Any] | None:
        """Serialize an approval record."""
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
    def serialize_publication_batch(
        batch: PublicationBatchModel | None,
    ) -> dict[str, Any] | None:
        """Serialize a publication batch."""
        if batch is None:
            return None
        return {
            "id": batch.id,
            "status": batch.status,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at,
        }

    @staticmethod
    def serialize_publication_deliveries(
        deliveries: list[PublicationDeliveryModel],
    ) -> list[dict[str, Any]]:
        """Serialize publication deliveries."""
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
    def serialize_details(
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
        """Serialize complete run details response."""
        return {
            "run_id": run.id,
            "session_id": snapshot.session_id,
            "scenario_key": snapshot.scenario_key,
            "lifecycle_state": run.lifecycle_state,
            "run_version": run.version_id,
            "selected_candidate_id": run.selected_candidate_id,
            "snapshot_hash": snapshot.canonical_input_hash,
            "gir": gir.gir_data if gir else None,
            "candidates": cls.serialize_candidates(candidates, rejections),
            "generation_provenance": generation.provenance if generation else None,
            "variants": cls.serialize_variants(variants),
            "diagnostics": cls.serialize_diagnostics(diagnostics),
            "simulation": simulation.metrics if simulation else None,
            "approval": cls.serialize_approval(approval),
            "publication_batch": cls.serialize_publication_batch(publication_batch),
            "publication_deliveries": cls.serialize_publication_deliveries(
                publication_deliveries
            ),
            "expected_bundle_hash": expected_hash,
            "decision_bundle_hash": run.decision_bundle_hash,
        }

    @staticmethod
    def serialize_snapshot(snapshot: SnapshotModel) -> dict[str, Any]:
        """Serialize a venue state snapshot."""
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

    @staticmethod
    def serialize_audit_event(item: AuditEventModel) -> dict[str, Any]:
        """Serialize an audit event."""
        return {
            "id": item.id,
            "sequence_number": item.sequence_number,
            "event_type": item.event_type,
            "payload": item.payload,
            "created_at": item.created_at,
            "previous_event_hash": item.previous_event_hash,
            "event_hash": item.event_hash,
        }
