from __future__ import annotations

from uuid import UUID

from backend.app.services.audit_service import AuditService
from backend.app.services.golden_flow.approval_workflow import ApprovalWorkflow
from backend.app.services.golden_flow.common import OwnershipError, RunNotFoundError
from backend.app.services.golden_flow.read_queries import ReadQueries
from backend.app.services.golden_flow.read_serializers import ReadSerializers
from backend.app.services.golden_flow.read_types import (
    AuditEventView,
    GoldenFlowDetailsResponse,
    SnapshotView,
)
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from sqlalchemy.ext.asyncio import AsyncSession


class ReadModel:
    @classmethod
    async def details(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> GoldenFlowDetailsResponse:
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id)
        candidates = await ReadQueries.run_candidates(db, run_id)
        rejections = await ReadQueries.rejections_by_candidate(db, candidates)
        gir = await ReadQueries.current_gir_model(db, run_id)
        generation = await ReadQueries.read_latest_generation(db, run_id)
        variants, diagnostics = await ReadQueries.generation_details(db, generation)
        simulation = await ReadQueries.latest_simulation(db, run.selected_candidate_id)
        approval = await ReadQueries.approval_record(db, run_id)
        publication_batch, publication_deliveries = (
            await ReadQueries.latest_publication(db, run_id)
        )
        expected_hash = await ApprovalWorkflow.expected_bundle_hash(
            db, run_id=run_id, session_id=session_id
        )
        return ReadSerializers.serialize_details(
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

    @staticmethod
    async def snapshot_details(
        db: AsyncSession, *, snapshot_id: UUID, session_id: UUID
    ) -> SnapshotView:
        snapshot = await ReadQueries.snapshot_by_id(db, snapshot_id)
        if snapshot is None:
            raise RunNotFoundError("Snapshot not found.")
        if snapshot.session_id != session_id:
            raise OwnershipError("Session does not own this snapshot.")
        return ReadSerializers.serialize_snapshot(snapshot)

    @classmethod
    async def audit_timeline(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, UUID | str | int | bool | list[AuditEventView]]:
        await RunWorkflow._owned_run(db, run_id, session_id)
        session_events = await ReadQueries.audit_events_for_session(db, session_id)
        events = [item for item in session_events if item.run_id == run_id]
        return {
            "run_id": run_id,
            "chain_scope": "session",
            "session_event_count": len(session_events),
            "chain_valid": AuditService.verify_chain(session_events),
            "events": [ReadSerializers.serialize_audit_event(item) for item in events],
        }
