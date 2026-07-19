"""Database query layer for read-model operations.

Pure SQLAlchemy queries for fetching run data without serialization or orchestration.
Returns persistence models and narrow internal query result objects only.
"""

from __future__ import annotations

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
from backend.app.persistence.models.run import (
    PublicationBatchModel,
    PublicationDeliveryModel,
    SimulationRunModel,
)
from backend.app.persistence.models.run import VenueStateSnapshot as SnapshotModel


class ReadQueries:
    """Database queries for run details, guidance, simulations, and approvals."""

    @staticmethod
    async def run_candidates(db: AsyncSession, run_id: UUID) -> list[CandidateModel]:
        """Fetch all intervention candidates for a run."""
        result = await db.execute(
            select(CandidateModel).where(CandidateModel.run_id == run_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def rejections_by_candidate(
        db: AsyncSession, candidates: list[CandidateModel]
    ) -> dict[UUID, list[CandidateRejectionModel]]:
        """Group candidate rejections by candidate ID."""
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
    async def current_gir_model(
        db: AsyncSession, run_id: UUID
    ) -> GIRVersionModel | None:
        """Fetch the current GIR version for a run."""
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
    async def read_latest_generation(
        db: AsyncSession, run_id: UUID
    ) -> GenerationRun | None:
        """Fetch the latest generation run for a preflight run."""
        result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def generation_details(
        db: AsyncSession, generation: GenerationRun | None
    ) -> tuple[list[GuidanceVariantModel], list[DiagnosticModel]]:
        """Fetch guidance variants and diagnostics for a generation."""
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
    async def latest_simulation(
        db: AsyncSession, candidate_id: UUID | None
    ) -> SimulationRunModel | None:
        """Fetch the latest simulation for a candidate."""
        result = await db.execute(
            select(SimulationRunModel)
            .where(SimulationRunModel.candidate_id == candidate_id)
            .order_by(SimulationRunModel.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def approval_record(
        db: AsyncSession, run_id: UUID
    ) -> ApprovalRecordModel | None:
        """Fetch the approval record for a run."""
        result = await db.execute(
            select(ApprovalRecordModel).where(ApprovalRecordModel.run_id == run_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def latest_publication(
        db: AsyncSession, run_id: UUID
    ) -> tuple[PublicationBatchModel | None, list[PublicationDeliveryModel]]:
        """Fetch the latest publication batch and its deliveries."""
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
    async def audit_events_for_session(
        db: AsyncSession, session_id: UUID
    ) -> list[AuditEventModel]:
        """Fetch all audit events for a session in sequence order."""
        result = await db.execute(
            select(AuditEventModel)
            .where(AuditEventModel.session_id == session_id)
            .order_by(AuditEventModel.sequence_number)
        )
        return list(result.scalars().all())

    @staticmethod
    async def snapshot_by_id(
        db: AsyncSession, snapshot_id: UUID
    ) -> SnapshotModel | None:
        """Fetch a snapshot by ID."""
        return await db.get(SnapshotModel, snapshot_id)
