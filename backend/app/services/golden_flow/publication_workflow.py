from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.workflow import LifecycleState
from backend.app.persistence.models.run import (
    ActiveInstructionModel,
    ApprovalRecordModel,
    GenerationRun,
    GuidanceVariantModel,
)
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import (
    PublicationBatchModel,
    PublicationDeliveryModel,
)
from backend.app.persistence.models.run import VenueStateSnapshot as SnapshotModel
from backend.app.services.golden_flow.approval_workflow import ApprovalWorkflow
from backend.app.services.golden_flow.common import (
    TransitionError,
    ValidationError,
    append_event,
    transition_run,
)
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.integrity import domain_hash


class PublicationWorkflow:
    @staticmethod
    async def _publication_approval(
        db: AsyncSession, run_id: UUID
    ) -> ApprovalRecordModel:
        result = await db.execute(
            select(ApprovalRecordModel).where(ApprovalRecordModel.run_id == run_id)
        )
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ValidationError("Approval evidence is missing.")
        return approval

    @classmethod
    async def _validate_publication_bundle(
        cls,
        db: AsyncSession,
        *,
        run: RunModel,
        snapshot: SnapshotModel,
        approval: ApprovalRecordModel,
    ) -> None:
        payload = await ApprovalWorkflow._bundle_payload(
            db,
            run,
            snapshot,
            run_version_override=approval.run_version,
        )
        current_hash = domain_hash("CROWDCUE_APPROVAL_BUNDLE_V1", payload)
        if run.decision_bundle_hash != current_hash:
            raise TransitionError("Approved evidence bundle is stale or invalid.")
        if approval.bundle_hash != current_hash:
            raise TransitionError("Approved evidence bundle is stale or invalid.")

    @staticmethod
    async def _publication_variants(
        db: AsyncSession, run_id: UUID
    ) -> dict[tuple[str, str], GuidanceVariantModel]:
        generation_result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        generation = generation_result.scalar_one()
        variants_result = await db.execute(
            select(GuidanceVariantModel).where(
                GuidanceVariantModel.generation_run_id == generation.id,
                GuidanceVariantModel.is_current.is_(True),
            )
        )
        variants = list(variants_result.scalars().all())
        return {(item.language, item.channel): item for item in variants}

    @staticmethod
    def _delivered(
        *,
        batch_id: UUID,
        surface: str,
        language: str,
        variant_id: UUID | None,
    ) -> PublicationDeliveryModel:
        return PublicationDeliveryModel(
            batch_id=batch_id,
            surface=surface,
            language=language,
            variant_id=variant_id,
            status="DELIVERED",
            delivered_at=datetime.now(timezone.utc),
        )

    @classmethod
    def _build_deliveries(
        cls,
        batch_id: UUID,
        variants: dict[tuple[str, str], GuidanceVariantModel],
    ) -> list[PublicationDeliveryModel]:
        deliveries: list[PublicationDeliveryModel] = []
        for language in ("en", "es", "fr"):
            fan_variant = variants[(language, "fan_app")]
            pa_variant = variants[(language, "pa")]
            deliveries.extend(
                (
                    cls._delivered(
                        batch_id=batch_id,
                        surface="FAN_APP",
                        language=language,
                        variant_id=fan_variant.id,
                    ),
                    cls._delivered(
                        batch_id=batch_id,
                        surface="PA",
                        language=language,
                        variant_id=pa_variant.id,
                    ),
                    cls._delivered(
                        batch_id=batch_id,
                        surface="SIGNAGE",
                        language=language,
                        variant_id=fan_variant.id,
                    ),
                )
            )
        deliveries.append(
            cls._delivered(
                batch_id=batch_id,
                surface="VOLUNTEER_DEVICE",
                language="ops",
                variant_id=None,
            )
        )
        return deliveries

    @staticmethod
    def _serialize_deliveries(
        deliveries: list[PublicationDeliveryModel],
    ) -> list[dict[str, Any]]:
        return [
            {
                "surface": item.surface,
                "language": item.language,
                "status": item.status,
                "variant_id": item.variant_id,
                "delivered_at": (
                    item.delivered_at.isoformat() if item.delivered_at else None
                ),
            }
            for item in deliveries
        ]

    @classmethod
    async def publish(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.APPROVED:
            raise TransitionError("Run is not eligible for publication.")
        approval = await cls._publication_approval(db, run.id)
        await cls._validate_publication_bundle(
            db,
            run=run,
            snapshot=snapshot,
            approval=approval,
        )
        current = transition_run(run, LifecycleState.PUBLISHING)
        variants = await cls._publication_variants(db, run_id)
        batch = PublicationBatchModel(run_id=run_id, status="PUBLISHING")
        db.add(batch)
        await db.flush()
        deliveries = cls._build_deliveries(batch.id, variants)
        db.add_all(deliveries)
        batch.status = "PUBLISHED"
        batch.completed_at = datetime.now(timezone.utc)
        transition_run(run, LifecycleState.PUBLISHED)
        db.add(
            ActiveInstructionModel(
                run_id=run.id,
                venue_id=snapshot.venue_id,
                audience_json={"source": "current_gir", "run_id": str(run.id)},
            )
        )
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="PUBLICATION_COMPLETED",
            payload={
                "from_state": current.value,
                "to_state": LifecycleState.PUBLISHED.value,
                "batch_id": str(batch.id),
                "delivery_count": len(deliveries),
                "simulated": True,
            },
        )
        await db.commit()
        return {
            "run_id": run.id,
            "lifecycle_state": run.lifecycle_state,
            "publication_batch_id": batch.id,
            "simulated": True,
            "deliveries": cls._serialize_deliveries(deliveries),
        }
