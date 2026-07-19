from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.gir import (
    GIR,
    AudienceScope,
    Directive,
    DirectiveAction,
    FallbackPolicy,
)
from backend.app.domain.workflow import (
    DirectiveStrength,
    LifecycleState,
)
from backend.app.persistence.models.run import (
    CandidateRejection as CandidateRejectionModel,
)
from backend.app.persistence.models.run import (
    GIRVersionModel,
)
from backend.app.persistence.models.run import InterventionCandidate as CandidateModel
from backend.app.persistence.models.run import OperationalIntent as IntentModel
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import Session as SessionModel
from backend.app.persistence.models.run import VenueStateSnapshot as SnapshotModel
from backend.app.persistence.models.venue import Route as RouteModel
from backend.app.persistence.models.venue import VenueNode
from backend.app.services.golden_flow.common import (
    OwnershipError,
    RunNotFoundError,
    ValidationError,
    append_event,
    transition_run,
)
from backend.app.services.integrity import domain_hash
from backend.app.services.reference_data_service import ReferenceDataService
from backend.app.services.simulation_service import SimulationService
from backend.app.services.venue_service import VenueService


class RunWorkflow:
    @staticmethod
    async def _owned_run(
        db: AsyncSession, run_id: UUID, session_id: UUID, *, lock: bool = False
    ) -> tuple[RunModel, SnapshotModel]:
        statement = select(RunModel).where(RunModel.id == run_id)
        if lock:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        run = result.scalar_one_or_none()
        if run is None:
            raise RunNotFoundError("Run not found.")
        snapshot_result = await db.execute(
            select(SnapshotModel).where(SnapshotModel.id == run.venue_state_snapshot_id)
        )
        snapshot = snapshot_result.scalar_one()
        if snapshot.session_id != session_id:
            raise OwnershipError("Session does not own this run.")
        return run, snapshot

    @staticmethod
    async def create_run(
        db: AsyncSession, *, session_id: UUID, scenario_key: str
    ) -> dict[str, Any]:
        topology = VenueService.load_topology()
        venue = await ReferenceDataService.ensure_seeded(db)
        session = await db.get(SessionModel, session_id)
        if session is None:
            session = SessionModel(
                id=session_id,
                active_scenario_key=scenario_key,
            )
            db.add(session)
            # These models use explicit foreign-key identifiers rather than ORM
            # relationships, so PostgreSQL needs the parent row persisted before
            # dependent snapshot and intent rows are flushed.
            await db.flush()
        else:
            session.active_scenario_key = scenario_key
        snapshot, intent, candidates = VenueService.evaluate_preflight(
            scenario_key, session_id
        )
        snapshot_model = SnapshotModel(
            id=snapshot.snapshot_id,
            session_id=session_id,
            venue_id=venue.id,
            scenario_key=scenario_key,
            reference_data_version=topology.reference_version,
            canonical_input_hash=snapshot.canonical_input_hash,
            timestamp=snapshot.timestamp,
            nodes_state=snapshot.nodes_state,
            edges_state=snapshot.edges_state,
            assets_state=snapshot.assets_state,
        )
        db.add(snapshot_model)
        intent_model = IntentModel(
            session_id=session_id,
            raw_text=f"{intent.objective} for {intent.target}",
            objective=intent.objective,
            target=intent.target,
            affected_audience=intent.affected_audience,
            constraints=intent.constraints,
            excluded_cohorts=list(intent.excluded_cohorts),
            confirmed=True,
        )
        db.add(intent_model)
        await db.flush()
        run = RunModel(
            intent_id=intent_model.id,
            venue_state_snapshot_id=snapshot.snapshot_id,
            lifecycle_state=LifecycleState.DRAFT.value,
            reference_data_version=topology.reference_version,
            terminology_version="2.0.0",
            simulation_policy_version=SimulationService.policy_version(),
            intervention_policy_version="1.1.0",
            compiler_version="2.0.0",
            fallback_template_version="2.0.0",
            sample_set_version="paired-v2",
        )
        db.add(run)
        await db.flush()
        for candidate in candidates:
            model = CandidateModel(
                id=candidate.id,
                run_id=run.id,
                candidate_key=candidate.candidate_key,
                title=candidate.title,
                destination_id=candidate.destination_id,
                route_id=candidate.route_id,
                cohort_id=candidate.cohort_id,
                is_viable=candidate.is_viable,
                preliminary_rank=candidate.preliminary_rank,
                policy_version=candidate.policy_version,
                selected=False,
            )
            db.add(model)
            # Candidate rejection rows carry raw candidate identifiers rather
            # than ORM relationships; persist each candidate parent first.
            await db.flush()
            for rejection in candidate.rejections:
                db.add(
                    CandidateRejectionModel(
                        id=rejection.id,
                        candidate_id=candidate.id,
                        reason_code=rejection.reason_code,
                        message=rejection.message,
                        affected_route_id=rejection.affected_route_id,
                        affected_edge_key=rejection.affected_edge_key,
                        affected_asset_key=rejection.affected_asset_key,
                    )
                )
        await append_event(
            db,
            session_id=session_id,
            run_id=run.id,
            event_type="RUN_CREATED",
            payload={
                "state": LifecycleState.DRAFT.value,
                "scenario_key": scenario_key,
                "synthetic_prototype": True,
            },
        )
        await db.commit()
        return {
            "run_id": run.id,
            "session_id": session_id,
            "scenario_key": scenario_key,
            "lifecycle_state": run.lifecycle_state,
            "snapshot_id": snapshot.snapshot_id,
            "canonical_input_hash": snapshot.canonical_input_hash,
            "candidates": [
                {
                    "id": item.id,
                    "candidate_key": item.candidate_key,
                    "title": item.title,
                    "cohort_id": item.cohort_id,
                    "is_viable": item.is_viable,
                    "preliminary_rank": item.preliminary_rank,
                    "rejections": [
                        rejection.model_dump(mode="json")
                        for rejection in item.rejections
                    ],
                }
                for item in candidates
            ],
        }

    @staticmethod
    async def _build_gir(
        db: AsyncSession,
        run: RunModel,
        snapshot: SnapshotModel,
        candidate: CandidateModel,
    ) -> GIR:
        intent = await db.get(IntentModel, run.intent_id)
        destination = await db.get(VenueNode, candidate.destination_id)
        route = await db.get(RouteModel, candidate.route_id)
        if intent is None or destination is None or route is None:
            raise ValidationError("Run references incomplete intent or topology data.")
        config = VenueService.candidate_config(
            snapshot.scenario_key, candidate.candidate_key
        )
        effective = snapshot.timestamp
        if effective.tzinfo is None or effective.utcoffset() is None:
            effective = effective.replace(tzinfo=timezone.utc)
        effective = effective.astimezone(timezone.utc).replace(microsecond=0)
        expiry = effective + timedelta(minutes=int(config.get("validity_minutes", 10)))
        fallback_destination = config.get("fallback_destination_key", "node-gate-b")
        gir = GIR(
            instruction_id=uuid5(run.id, "guidance-instruction"),
            version=1,
            venue_id=snapshot.venue_id,
            session_id=snapshot.session_id,
            intent_id=intent.id,
            candidate_id=candidate.id,
            venue_state_snapshot_id=snapshot.id,
            reference_data_version=run.reference_data_version,
            terminology_version=run.terminology_version,
            simulation_policy_version=run.simulation_policy_version,
            intervention_policy_version=run.intervention_policy_version,
            compiler_version=run.compiler_version,
            source_team="Venue Operations",
            audience=AudienceScope(
                sections=tuple(
                    config.get("audience_sections", ["114", "115", "116", "117"])
                ),
                approach_zones=tuple(config.get("approach_zones", ["node-plaza-west"])),
                cohort_id=candidate.cohort_id,
            ),
            directive=Directive(
                action=DirectiveAction(config.get("directive_action", "REDIRECT")),
                strength=DirectiveStrength(
                    config.get("directive_strength", "RECOMMENDED")
                ),
            ),
            destination_id=destination.stable_key,
            route=tuple(route.waypoints),
            excluded_cohorts=tuple(
                config.get("excluded_cohorts", ["mobility-assistance-cohort"])
            ),
            protected_route_ids=tuple(
                config.get("protected_route_keys", ["route-mobility-protected"])
            ),
            required_asset_ids=tuple(config.get("required_asset_keys", [])),
            fallback=FallbackPolicy(
                action=DirectiveAction(config.get("fallback_action", "REDIRECT")),
                destination_id=fallback_destination,
            ),
            effective_time=effective,
            expiry_time=expiry,
            lifecycle_state=LifecycleState.CANDIDATE_SELECTED,
        )
        hash_value = domain_hash(
            "CROWDCUE_GIR_V1", gir.model_dump(exclude={"content_hash"})
        )
        return gir.model_copy(update={"content_hash": hash_value})

    @classmethod
    async def select_candidate(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        candidate_id: UUID,
    ) -> dict[str, Any]:
        run, snapshot = await RunWorkflow._owned_run(db, run_id, session_id, lock=True)
        current = transition_run(run, LifecycleState.CANDIDATE_SELECTED)
        result = await db.execute(
            select(CandidateModel).where(
                CandidateModel.id == candidate_id,
                CandidateModel.run_id == run_id,
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            raise ValidationError("Candidate does not belong to this run.")
        if not candidate.is_viable:
            raise ValidationError("Rejected candidate cannot be selected.")
        await db.execute(
            update(CandidateModel)
            .where(CandidateModel.run_id == run_id)
            .values(selected=False)
        )
        candidate.selected = True
        run.selected_candidate_id = candidate.id
        gir = await RunWorkflow._build_gir(db, run, snapshot, candidate)
        db.add(
            GIRVersionModel(
                run_id=run.id,
                instruction_id=gir.instruction_id,
                version=gir.version,
                gir_data=gir.model_dump(mode="json"),
                content_hash=gir.content_hash,
                is_current=True,
            )
        )
        await append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="CANDIDATE_SELECTED",
            payload={
                "from_state": current.value,
                "to_state": LifecycleState.CANDIDATE_SELECTED.value,
                "candidate_id": str(candidate.id),
                "candidate_key": candidate.candidate_key,
                "gir_hash": gir.content_hash,
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "selected_candidate_id": candidate.id,
            "lifecycle_state": run.lifecycle_state,
            "gir": gir.model_dump(mode="json"),
        }
