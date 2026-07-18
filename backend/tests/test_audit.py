import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.audit import AuditEventModel
from backend.app.persistence.models.run import Session
from backend.app.persistence.models.venue import ReferenceDataVersion, Venue
from backend.app.services.audit_service import (
    GENESIS_HASH,
    AuditService,
    compute_audit_hash,
)


async def test_audit_hash_chain_creation(db_session: AsyncSession):
    # Setup session
    ref = ReferenceDataVersion(version_key="v1_test_audit", hash="dummy_hash")
    db_session.add(ref)
    await db_session.flush()

    venue = Venue(name="Venue Test", ref_version="v1_test_audit")
    db_session.add(venue)
    await db_session.flush()

    session_obj = Session(active_scenario_key="gate_convergence")
    db_session.add(session_obj)
    await db_session.flush()

    # Append first event (sequence 0)
    evt0 = await AuditService.append_event(
        db_session,
        session_id=session_obj.id,
        run_id=None,
        event_type="SESSION_START",
        payload={"scenario": "gate_convergence"},
    )
    assert evt0.sequence_number == 0
    assert evt0.previous_event_hash == GENESIS_HASH

    # Append second event (sequence 1)
    evt1 = await AuditService.append_event(
        db_session,
        session_id=session_obj.id,
        run_id=None,
        event_type="INTENT_DECLARED",
        payload={"raw_text": "Clear gates"},
    )
    assert evt1.sequence_number == 1
    assert evt1.previous_event_hash == evt0.event_hash

    # Verify chain hashes manually
    expected_evt0_hash = compute_audit_hash(
        GENESIS_HASH,
        {"scenario": "gate_convergence"},
        "SESSION_START",
        evt0.created_at.isoformat(),
        0,
    )
    assert evt0.event_hash == expected_evt0_hash

    expected_evt1_hash = compute_audit_hash(
        evt0.event_hash,
        {"raw_text": "Clear gates"},
        "INTENT_DECLARED",
        evt1.created_at.isoformat(),
        1,
    )
    assert evt1.event_hash == expected_evt1_hash


async def test_audit_sequence_constraint(db_session: AsyncSession):
    ref = ReferenceDataVersion(
        version_key="v1_test_audit_constraint", hash="dummy_hash"
    )
    db_session.add(ref)
    await db_session.flush()

    venue = Venue(name="Venue Test", ref_version="v1_test_audit_constraint")
    db_session.add(venue)
    await db_session.flush()

    session_obj = Session(active_scenario_key="gate_convergence")
    db_session.add(session_obj)
    await db_session.flush()

    # Add sequence 0 event
    evt0 = AuditEventModel(
        session_id=session_obj.id,
        event_type="EVT",
        payload={},
        sequence_number=0,
        previous_event_hash=GENESIS_HASH,
        event_hash="hash0",
    )
    db_session.add(evt0)
    await db_session.flush()

    # Attempt to add another sequence 0 event in same session using a nested transaction
    async with db_session.begin_nested():
        evt_dup = AuditEventModel(
            session_id=session_obj.id,
            event_type="EVT_DUP",
            payload={},
            sequence_number=0,
            previous_event_hash=GENESIS_HASH,
            event_hash="hash_dup",
        )
        db_session.add(evt_dup)

        with pytest.raises(IntegrityError):
            await db_session.flush()
