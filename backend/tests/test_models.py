from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm.exc import StaleDataError

from backend.app.persistence.models.run import PreflightRun
from backend.app.services.golden_flow_service import GoldenFlowService
from backend.tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_optimistic_concurrency_preflight_run(db_session) -> None:
    created = await GoldenFlowService.create_run(
        db_session, session_id=uuid4(), scenario_key="gate_convergence"
    )
    run_id = created["run_id"]

    async with TestSessionLocal() as first, TestSessionLocal() as second:
        first_run = await first.get(PreflightRun, run_id)
        second_run = await second.get(PreflightRun, run_id)
        assert first_run is not None and second_run is not None
        first_run.lifecycle_state = "CANDIDATE_SELECTED"
        await first.commit()
        second_run.lifecycle_state = "GUIDANCE_VERIFYING"
        with pytest.raises(StaleDataError):
            await second.commit()
