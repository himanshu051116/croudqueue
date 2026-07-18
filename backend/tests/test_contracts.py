from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.audit import AuditEventModel
from backend.app.persistence.models.run import (
    CandidateRejection,
    GenerationRun,
    GIRVersionModel,
    GuidanceVariantModel,
    IdempotencyKeyModel,
    InterventionCandidate,
    OperationalIntent,
    OutboxEventModel,
    PreflightRun,
    VenueStateSnapshot,
)
from backend.app.persistence.models.venue import (
    ReferenceDataVersion,
    Venue,
    VenueNode,
)
from backend.app.services.audit_service import AuditService
from backend.app.services.golden_flow_service import GoldenFlowService
from backend.app.services.reference_data_service import (
    ReferenceDataIntegrityError,
    ReferenceDataService,
)
from backend.app.services.venue_service import VenueService


async def test_reference_data_seed_is_idempotent(db_session: AsyncSession) -> None:
    first = await ReferenceDataService.ensure_seeded(db_session)
    second = await ReferenceDataService.ensure_seeded(db_session)
    await db_session.commit()
    assert first.id == second.id
    venue_count = await db_session.scalar(select(func.count()).select_from(Venue))
    assert venue_count == 1


async def test_topology_keys_are_unique_per_venue_not_globally(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            ReferenceDataVersion(version_key="ref-a", hash="a" * 64),
            ReferenceDataVersion(version_key="ref-b", hash="b" * 64),
        ]
    )
    first = Venue(name="First", ref_version="ref-a")
    second = Venue(name="Second", ref_version="ref-b")
    db_session.add_all([first, second])
    await db_session.flush()
    db_session.add_all(
        [
            VenueNode(
                venue_id=first.id,
                name="Gate A",
                node_type="GATE",
                capacity=100,
                stable_key="gate-a",
            ),
            VenueNode(
                venue_id=second.id,
                name="Gate A",
                node_type="GATE",
                capacity=100,
                stable_key="gate-a",
            ),
        ]
    )
    await db_session.flush()
    duplicate = VenueNode(
        venue_id=first.id,
        name="Duplicate",
        node_type="GATE",
        capacity=100,
        stable_key="gate-a",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_create_run_persists_authoritative_inputs_and_candidates(
    db_session: AsyncSession,
) -> None:
    session_id = uuid4()
    result = await GoldenFlowService.create_run(
        db_session, session_id=session_id, scenario_key="gate_convergence"
    )
    run = await db_session.get(PreflightRun, result["run_id"])
    assert run is not None
    snapshot = await db_session.get(VenueStateSnapshot, run.venue_state_snapshot_id)
    intent = await db_session.get(OperationalIntent, run.intent_id)
    assert snapshot is not None and len(snapshot.canonical_input_hash) == 64
    assert snapshot.session_id == session_id
    assert intent is not None and intent.confirmed is True
    candidates = list(
        (
            await db_session.execute(
                select(InterventionCandidate).where(
                    InterventionCandidate.run_id == run.id
                )
            )
        ).scalars()
    )
    assert len(candidates) >= 3
    rejection_count = await db_session.scalar(
        select(func.count())
        .select_from(CandidateRejection)
        .join(InterventionCandidate)
        .where(InterventionCandidate.run_id == run.id)
    )
    assert rejection_count and rejection_count >= 1


async def test_selected_candidate_creates_immutable_gir_version(
    db_session: AsyncSession,
) -> None:
    session_id = uuid4()
    created = await GoldenFlowService.create_run(
        db_session, session_id=session_id, scenario_key="gate_convergence"
    )
    candidate = next(
        item
        for item in created["candidates"]
        if item["candidate_key"] == "cand-west-gate-a"
    )
    await GoldenFlowService.select_candidate(
        db_session,
        run_id=created["run_id"],
        session_id=session_id,
        candidate_id=candidate["id"],
    )
    girs = list(
        (
            await db_session.execute(
                select(GIRVersionModel).where(
                    GIRVersionModel.run_id == created["run_id"]
                )
            )
        ).scalars()
    )
    assert len(girs) == 1
    assert girs[0].version == 1 and girs[0].is_current is True
    assert len(girs[0].content_hash) == 64


async def test_audit_chain_and_outbox_are_written_together(
    db_session: AsyncSession,
) -> None:
    created = await GoldenFlowService.create_run(
        db_session, session_id=uuid4(), scenario_key="gate_convergence"
    )
    events = list(
        (
            await db_session.execute(
                select(AuditEventModel)
                .where(AuditEventModel.run_id == created["run_id"])
                .order_by(AuditEventModel.sequence_number)
            )
        ).scalars()
    )
    outbox = [
        item
        for item in (await db_session.execute(select(OutboxEventModel))).scalars()
        if item.payload.get("run_id") == str(created["run_id"])
    ]
    assert AuditService.verify_chain(events)
    assert events and outbox


async def test_idempotency_primary_key_rejects_duplicate(
    db_session: AsyncSession,
) -> None:
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    first = IdempotencyKeyModel(
        key_hash="1" * 64,
        request_hash="2" * 64,
        command_type="CREATE_RUN",
        status="COMPLETED",
        expires_at=expires,
    )
    db_session.add(first)
    await db_session.commit()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            insert(IdempotencyKeyModel).values(
                key_hash="1" * 64,
                request_hash="3" * 64,
                command_type="CREATE_RUN",
                status="COMPLETED",
                expires_at=expires,
            )
        )
        await db_session.commit()


async def test_guidance_storage_is_normalized_by_language_channel_and_version(
    db_session: AsyncSession,
) -> None:
    session_id = uuid4()
    created = await GoldenFlowService.create_run(
        db_session, session_id=session_id, scenario_key="gate_convergence"
    )
    candidate = next(
        item
        for item in created["candidates"]
        if item["candidate_key"] == "cand-west-gate-a"
    )
    await GoldenFlowService.select_candidate(
        db_session,
        run_id=created["run_id"],
        session_id=session_id,
        candidate_id=candidate["id"],
    )
    generated = await GoldenFlowService.generate_guidance(
        db_session,
        run_id=created["run_id"],
        session_id=session_id,
        enable_fault_injection=True,
    )
    assert len(generated["variants"]) == 6
    generation = (
        await db_session.execute(
            select(GenerationRun).where(
                GenerationRun.preflight_run_id == created["run_id"]
            )
        )
    ).scalar_one()
    variants = list(
        (
            await db_session.execute(
                select(GuidanceVariantModel).where(
                    GuidanceVariantModel.generation_run_id == generation.id
                )
            )
        ).scalars()
    )
    assert len(variants) == 6
    assert len({(item.language, item.channel) for item in variants}) == 6


async def test_reference_version_hash_is_immutable(db_session: AsyncSession) -> None:
    topology = VenueService.load_topology()
    db_session.add(
        ReferenceDataVersion(
            version_key=topology.reference_version,
            hash="0" * 64,
        )
    )
    await db_session.commit()

    with pytest.raises(ReferenceDataIntegrityError, match="new reference version"):
        await ReferenceDataService.ensure_seeded(db_session)
