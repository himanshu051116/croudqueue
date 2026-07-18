from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.run import (
    IdempotencyKeyModel,
    OutboxEventModel,
    Session,
)


async def test_atomic_outbox_insertion(db_session: AsyncSession):
    # Start a transaction, insert both a business session and a related outbox event
    new_session = Session(active_scenario_key="gate_convergence")
    db_session.add(new_session)
    await db_session.flush()

    outbox_event = OutboxEventModel(
        event_type="SESSION_CREATED",
        payload={"session_id": str(new_session.id), "scenario": "gate_convergence"},
        delivery_status="PENDING",
    )
    db_session.add(outbox_event)
    await db_session.flush()

    # Query from db using same session to verify both persist
    session_res = await db_session.get(Session, new_session.id)
    outbox_res = await db_session.get(OutboxEventModel, outbox_event.id)

    assert session_res is not None
    assert outbox_res is not None
    assert outbox_res.event_type == "SESSION_CREATED"


async def test_idempotency_key_uniqueness(db_session: AsyncSession):
    # Insert idempotency key
    key = IdempotencyKeyModel(
        key_hash="unique_hash_12345",
        request_hash="req_hash_abc",
        command_type="SUBMIT_PREFLIGHT",
        status="LOCK_ACQUIRED",
        lock_acquired_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(key)
    await db_session.flush()

    # Attempt to insert identical key_hash using direct SQL insert in a nested transaction.
    # The pytest.raises block must wrap the entire begin_nested context manager so that
    # the savepoint is rolled back correctly on error.
    from sqlalchemy import insert

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                insert(IdempotencyKeyModel).values(
                    key_hash="unique_hash_12345",
                    request_hash="req_hash_xyz",
                    command_type="SUBMIT_PREFLIGHT",
                    status="LOCK_ACQUIRED",
                    lock_acquired_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
            )


async def test_outbox_atomic_rollback(db_session: AsyncSession) -> None:
    # 1. Verify rollback removes both state changes and outbox events
    new_session = Session(active_scenario_key="gate_convergence")
    db_session.add(new_session)
    await db_session.flush()

    outbox_event = OutboxEventModel(
        event_type="SESSION_CREATED",
        payload={"session_id": str(new_session.id)},
        delivery_status="PENDING",
    )
    db_session.add(outbox_event)
    await db_session.flush()

    # Rollback current transaction
    await db_session.rollback()

    # Query from db using same session to prove neither exists
    session_res = await db_session.get(Session, new_session.id)
    outbox_res = await db_session.get(OutboxEventModel, outbox_event.id)

    assert session_res is None
    assert outbox_res is None


async def test_outbox_event_claiming_lifecycle(db_session: AsyncSession) -> None:
    import uuid

    from sqlalchemy import delete

    from backend.app.services.outbox_dispatcher import OutboxDispatcher

    # Clear outbox table to ensure isolation
    await db_session.execute(delete(OutboxEventModel))
    await db_session.flush()

    # Insert a pending outbox event
    event = OutboxEventModel(
        event_type="TEST_EVENT",
        payload={"key": "val"},
        delivery_status="PENDING",
    )
    db_session.add(event)
    await db_session.flush()

    worker_a = uuid.uuid4()
    worker_b = uuid.uuid4()

    # 1. Claim pending event with worker A
    claimed = await OutboxDispatcher.claim_next_event(db_session, worker_a)
    assert claimed is not None
    assert claimed.id == event.id
    assert claimed.locked_by == worker_a
    assert claimed.delivery_status == "CLAIMED"
    await db_session.flush()

    # 2. Try to claim with worker B while locked (should yield None)
    claimed_b = await OutboxDispatcher.claim_next_event(db_session, worker_b)
    assert claimed_b is None

    # 3. Mark processed and verify status persistence
    await OutboxDispatcher.mark_processed(db_session, event.id)
    await db_session.flush()

    # 4. Verify processed state in db
    db_event = await db_session.get(OutboxEventModel, event.id)
    assert db_event is not None
    assert db_event.delivery_status == "PROCESSED"
    assert db_event.processed_at is not None
    assert db_event.locked_by is None
