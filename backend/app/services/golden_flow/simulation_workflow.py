from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.workflow import (
    LifecycleState,
)
from backend.app.persistence.models.run import InterventionCandidate as CandidateModel
from backend.app.persistence.models.run import (
    SimulationRunModel,
    SimulationSampleModel,
)
from backend.app.persistence.models.venue import Route as RouteModel
from backend.app.services.golden_flow.common import (
    ValidationError,
    append_event,
    transition_run,
)
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.simulation_service import SimulationService


class SimulationWorkflow:
    @classmethod
    async def simulate(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        current = transition_run(run, LifecycleState.SIMULATION_RUNNING)
        candidate = await db.get(CandidateModel, run.selected_candidate_id)
        if candidate is None:
            raise ValidationError("Selected candidate is missing.")
        route = await db.get(RouteModel, candidate.route_id)
        if route is None:
            raise ValidationError("Selected route is missing.")
        result = SimulationService.run_paired_simulation(
            snapshot.scenario_key,
            candidate.candidate_key,
            route.stable_key,
            candidate.cohort_id,
        )
        simulation = SimulationRunModel(
            candidate_id=candidate.id,
            sample_set_id=result["sample_set_id"],
            seed=result["seed"],
            samples_count=result["sample_count"],
            failure_frequency=result["failure_frequency"],
            wilson_lower=result["wilson_95_lower"],
            wilson_upper=result["wilson_95_upper"],
            verdict=result["verdict"],
            result_hash=result["result_hash"],
            metrics=result,
        )
        db.add(simulation)
        await db.flush()
        db.add(
            SimulationSampleModel(
                simulation_run_id=simulation.id,
                sample_key=result["sample_set_id"],
                metrics={
                    "samples_hash": result["samples_hash"],
                    "paired": result["paired"],
                    "seed": result["seed"],
                },
            )
        )
        if result["verdict"] == "BLOCK":
            transition_run(run, LifecycleState.PREFLIGHT_BLOCKED)
        else:
            transition_run(run, LifecycleState.PREFLIGHT_PASSED)
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="SIMULATION_COMPLETED",
            payload={
                "from_state": current.value,
                "to_state": run.lifecycle_state,
                "sample_set_id": result["sample_set_id"],
                "result_hash": result["result_hash"],
                "verdict": result["verdict"],
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "simulation": result,
        }
