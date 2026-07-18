from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid5

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.domain.diagnostics import Diagnostic
from backend.app.domain.gir import (
    GIR,
    AudienceScope,
    Directive,
    DirectiveAction,
    FallbackPolicy,
)
from backend.app.domain.guidance import (
    GuidanceChannel,
    GuidanceVariant,
    Language,
)
from backend.app.domain.workflow import (
    DirectiveStrength,
    LifecycleState,
    validate_transition,
)
from backend.app.persistence.models.audit import AuditEventModel
from backend.app.persistence.models.run import (
    ActiveInstructionModel,
    ApprovalRecordModel,
)
from backend.app.persistence.models.run import (
    CandidateRejection as CandidateRejectionModel,
)
from backend.app.persistence.models.run import (
    CompilerResultModel,
    DiagnosticModel,
    GenerationRun,
    GIRVersionModel,
    GuidanceVariantModel,
)
from backend.app.persistence.models.run import InterventionCandidate as CandidateModel
from backend.app.persistence.models.run import OperationalIntent as IntentModel
from backend.app.persistence.models.run import (
    OutboxEventModel,
)
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.persistence.models.run import (
    PublicationBatchModel,
    PublicationDeliveryModel,
    RepairAttemptModel,
    SemanticComparisonModel,
)
from backend.app.persistence.models.run import Session as SessionModel
from backend.app.persistence.models.run import (
    SimulationRunModel,
    SimulationSampleModel,
)
from backend.app.persistence.models.run import VenueStateSnapshot as SnapshotModel
from backend.app.persistence.models.venue import Route as RouteModel
from backend.app.persistence.models.venue import VenueNode
from backend.app.services.audit_service import AuditService
from backend.app.services.guidance import GuidanceService
from backend.app.services.guidance.reverse_compiler import reverse_compile_guidance
from backend.app.services.integrity import domain_hash
from backend.app.services.reference_data_service import ReferenceDataService
from backend.app.services.simulation_service import SimulationService
from backend.app.services.venue_service import VenueService


class RunNotFoundError(LookupError):
    pass


class OwnershipError(PermissionError):
    pass


class TransitionError(RuntimeError):
    pass


class ValidationError(RuntimeError):
    pass


def _transition(run: RunModel, target: LifecycleState) -> LifecycleState:
    current = LifecycleState(run.lifecycle_state)
    if not validate_transition(current, target):
        raise TransitionError(
            f"Invalid transition from {current.value} to {target.value}."
        )
    run.lifecycle_state = target.value
    return current


async def _append_event(
    db: AsyncSession,
    *,
    session_id: UUID,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    await AuditService.append_event(db, session_id, run_id, event_type, payload)
    db.add(
        OutboxEventModel(
            event_type=event_type,
            payload={"session_id": str(session_id), "run_id": str(run_id), **payload},
            delivery_status="PENDING",
        )
    )
    await db.flush()


class GoldenFlowService:
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
        await _append_event(
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
        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        current = _transition(run, LifecycleState.CANDIDATE_SELECTED)
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
        gir = await cls._build_gir(db, run, snapshot, candidate)
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
        await _append_event(
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

    @staticmethod
    async def _current_gir(
        db: AsyncSession, run_id: UUID
    ) -> tuple[GIRVersionModel, GIR]:
        result = await db.execute(
            select(GIRVersionModel)
            .where(
                GIRVersionModel.run_id == run_id, GIRVersionModel.is_current.is_(True)
            )
            .order_by(GIRVersionModel.version.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValidationError("Current GIR is missing.")
        return model, GIR.model_validate(model.gir_data)

    @staticmethod
    async def _persist_compilation(
        db: AsyncSession,
        *,
        run: RunModel,
        generation: GenerationRun,
        variant_model: GuidanceVariantModel,
        variant: GuidanceVariant,
        gir: GIR,
        diagnostics: list[Diagnostic],
    ) -> None:
        meaning = reverse_compile_guidance(variant)
        compiler_hash = domain_hash("CROWDCUE_COMPILED_MEANING_V1", meaning)
        compiler = CompilerResultModel(
            variant_id=variant_model.id,
            compiled_meaning=meaning.model_dump(mode="json"),
            compiler_version=run.compiler_version,
            result_hash=compiler_hash,
        )
        db.add(compiler)
        await db.flush()
        variant_diagnostics = [
            item
            for item in diagnostics
            if item.language == variant.language.value
            and item.channel == variant.channel.value
        ]
        differences = [item.model_dump(mode="json") for item in variant_diagnostics]
        comparison_hash = domain_hash(
            "CROWDCUE_SEMANTIC_COMPARISON_V1",
            {"compiled": compiler_hash, "differences": differences},
        )
        db.add(
            SemanticComparisonModel(
                compiler_result_id=compiler.id,
                differences=differences,
                is_equivalent=not variant_diagnostics,
                result_hash=comparison_hash,
            )
        )
        for item in variant_diagnostics:
            db.add(
                DiagnosticModel(
                    generation_run_id=generation.id,
                    variant_id=variant_model.id,
                    stage=item.stage.value,
                    severity=item.severity.value,
                    code=item.code,
                    message=item.message,
                    details=jsonable_encoder(item.model_dump()),
                    blocking=item.blocking,
                )
            )

    @classmethod
    async def generate_guidance(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        enable_fault_injection: bool,
        guidance_service: GuidanceService | None = None,
    ) -> dict[str, Any]:
        if enable_fault_injection and not settings.ENABLE_DEMO_FAULT_INJECTION:
            raise ValidationError(
                "Demo fault injection is disabled by server configuration."
            )
        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        current = _transition(run, LifecycleState.GUIDANCE_VERIFYING)
        await _append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="GUIDANCE_VERIFICATION_STARTED",
            payload={"from_state": current.value, "to_state": run.lifecycle_state},
        )
        await db.commit()

        _, gir = await cls._current_gir(db, run_id)
        service = guidance_service or GuidanceService()
        started_at = datetime.now(timezone.utc)
        try:
            result = await service.generate_and_verify_guidance(
                gir, enable_fault_injection=enable_fault_injection
            )
        except Exception as exc:
            run, _ = await cls._owned_run(db, run_id, session_id, lock=True)
            if LifecycleState(run.lifecycle_state) is LifecycleState.GUIDANCE_VERIFYING:
                failed_from = _transition(run, LifecycleState.CANDIDATE_SELECTED)
                await _append_event(
                    db,
                    session_id=session_id,
                    run_id=run_id,
                    event_type="GUIDANCE_GENERATION_FAILED",
                    payload={
                        "from_state": failed_from.value,
                        "to_state": LifecycleState.CANDIDATE_SELECTED.value,
                        "safe_error_code": type(exc).__name__,
                        "retry_allowed": True,
                    },
                )
                await db.commit()
            raise
        completed_at = datetime.now(timezone.utc)

        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.GUIDANCE_VERIFYING:
            raise TransitionError("Run changed while guidance was generated.")
        generation = GenerationRun(
            preflight_run_id=run_id,
            model_used=result.provenance.get("model") or settings.GEMINI_MODEL,
            provider=result.provenance["provider"],
            status="BLOCKED" if result.diagnostics else "PASSED",
            fallback_used=result.fallback_used,
            request_count=int(result.provenance.get("request_count", 0)),
            successful_request_count=int(
                result.provenance.get("successful_request_count", 0)
            ),
            attempt_count=int(result.provenance.get("attempt_count", 0)),
            safe_error_code=result.provenance.get("safe_error_code"),
            request_id_hash=result.provenance.get("request_id_hash"),
            provenance=jsonable_encoder(result.provenance),
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=int(result.provenance.get("latency_ms", 0)),
        )
        db.add(generation)
        await db.flush()
        persisted: list[tuple[GuidanceVariantModel, GuidanceVariant]] = []
        for variant in result.variants:
            model = GuidanceVariantModel(
                generation_run_id=generation.id,
                language=variant.language.value,
                channel=variant.channel.value,
                version=variant.version,
                audience_action=variant.audience_action,
                route_clause=variant.route_clause,
                fallback_clause=variant.fallback_clause,
                protection_clause=variant.protection_clause,
                validity_clause=variant.validity_clause,
                optional_explanation=variant.optional_explanation,
                rendered_text=variant.rendered_text,
                content_hash=variant.content_hash,
                is_current=True,
            )
            db.add(model)
            await db.flush()
            persisted.append((model, variant))
        for model, variant in persisted:
            await cls._persist_compilation(
                db,
                run=run,
                generation=generation,
                variant_model=model,
                variant=variant,
                gir=gir,
                diagnostics=result.diagnostics,
            )

        target = (
            LifecycleState.PREFLIGHT_BLOCKED
            if any(item.blocking for item in result.diagnostics)
            else LifecycleState.SEMANTIC_PASSED
        )
        from_state = _transition(run, target)
        event_type = "SEMANTIC_BLOCKED" if result.diagnostics else "SEMANTIC_PASSED"
        if result.provenance.get("fault_injection"):
            await _append_event(
                db,
                session_id=session_id,
                run_id=run_id,
                event_type="DEMO_FAULT_INJECTED",
                payload={"fault_code": result.provenance.get("fault_code")},
            )
        await _append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            payload={
                "from_state": from_state.value,
                "to_state": target.value,
                "diagnostic_codes": [item.code for item in result.diagnostics],
                "provenance": result.provenance,
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "variants": [item.model_dump(mode="json") for item in result.variants],
            "diagnostics": [
                item.model_dump(mode="json") for item in result.diagnostics
            ],
            "provenance": result.provenance,
        }

    @classmethod
    async def repair(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        current = _transition(run, LifecycleState.GUIDANCE_VERIFYING)
        generation_result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        generation = generation_result.scalar_one_or_none()
        if generation is None:
            raise ValidationError("No guidance generation exists.")
        variant_result = await db.execute(
            select(GuidanceVariantModel).where(
                GuidanceVariantModel.generation_run_id == generation.id,
                GuidanceVariantModel.is_current.is_(True),
            )
        )
        models = list(variant_result.scalars().all())
        variants = [
            GuidanceVariant(
                language=Language(model.language),
                channel=GuidanceChannel(model.channel),
                version=model.version,
                audience_action=model.audience_action,
                route_clause=model.route_clause,
                fallback_clause=model.fallback_clause,
                protection_clause=model.protection_clause,
                validity_clause=model.validity_clause,
                optional_explanation=model.optional_explanation,
                rendered_text=model.rendered_text,
                content_hash=model.content_hash,
            )
            for model in models
        ]
        _, gir = await cls._current_gir(db, run_id)
        repaired_variants, diagnostics = GuidanceService.repair_variant(variants, gir)
        target_old = next(
            model
            for model in models
            if model.language == "es" and model.channel == "fan_app"
        )
        repaired = next(
            item
            for item in repaired_variants
            if item.language.value == "es" and item.channel.value == "fan_app"
        )
        blocking_result = await db.execute(
            select(DiagnosticModel)
            .where(
                DiagnosticModel.generation_run_id == generation.id,
                DiagnosticModel.blocking.is_(True),
                DiagnosticModel.code == "PROTECTED_COHORT_OMITTED",
            )
            .order_by(DiagnosticModel.id)
        )
        blocking_diagnostic = blocking_result.scalars().first()
        if blocking_diagnostic is None:
            raise ValidationError("Repair target diagnostic is missing.")
        target_old.is_current = False
        new_model = GuidanceVariantModel(
            generation_run_id=generation.id,
            language=repaired.language.value,
            channel=repaired.channel.value,
            version=repaired.version,
            audience_action=repaired.audience_action,
            route_clause=repaired.route_clause,
            fallback_clause=repaired.fallback_clause,
            protection_clause=repaired.protection_clause,
            validity_clause=repaired.validity_clause,
            optional_explanation=repaired.optional_explanation,
            rendered_text=repaired.rendered_text,
            content_hash=repaired.content_hash,
            is_current=True,
        )
        db.add(new_model)
        await db.flush()
        db.add(
            RepairAttemptModel(
                variant_id=target_old.id,
                diagnostic_id=blocking_diagnostic.id,
                target_clause="protection_clause",
                original_text=target_old.protection_clause,
                repaired_text=repaired.protection_clause,
                generation_run_id=generation.id,
                succeeded=not diagnostics,
            )
        )
        blocking_diagnostic.blocking = False
        blocking_diagnostic.resolved_at = datetime.now(timezone.utc)
        await cls._persist_compilation(
            db,
            run=run,
            generation=generation,
            variant_model=new_model,
            variant=repaired,
            gir=gir,
            diagnostics=diagnostics,
        )
        if diagnostics:
            run.lifecycle_state = LifecycleState.PREFLIGHT_BLOCKED.value
        else:
            _transition(run, LifecycleState.SEMANTIC_PASSED)
        unchanged_hashes = {
            f"{model.language}:{model.channel}": model.content_hash
            for model in models
            if model.id != target_old.id
        }
        unchanged_spanish_clauses = all(
            (
                target_old.audience_action == repaired.audience_action,
                target_old.route_clause == repaired.route_clause,
                target_old.fallback_clause == repaired.fallback_clause,
                target_old.validity_clause == repaired.validity_clause,
                (target_old.optional_explanation or "")
                == (repaired.optional_explanation or ""),
            )
        )
        if not unchanged_spanish_clauses:
            raise ValidationError("Targeted repair changed an unrelated clause.")
        await _append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="TARGETED_REPAIR_COMPLETED",
            payload={
                "from_state": current.value,
                "to_state": run.lifecycle_state,
                "original_variant_id": str(target_old.id),
                "repaired_variant_id": str(new_model.id),
                "target_clause": "protection_clause",
                "unaffected_variant_hashes": unchanged_hashes,
                "unaffected_spanish_clauses_unchanged": (unchanged_spanish_clauses),
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "repaired_variant": repaired.model_dump(mode="json"),
            "original_variant_id": target_old.id,
            "repaired_variant_id": new_model.id,
            "unaffected_variant_hashes": unchanged_hashes,
            "unaffected_spanish_clauses_unchanged": unchanged_spanish_clauses,
            "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
        }

    @classmethod
    async def simulate(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        current = _transition(run, LifecycleState.SIMULATION_RUNNING)
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
            _transition(run, LifecycleState.PREFLIGHT_BLOCKED)
        else:
            _transition(run, LifecycleState.PREFLIGHT_PASSED)
        await _append_event(
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

    @classmethod
    async def _bundle_payload(
        cls,
        db: AsyncSession,
        run: RunModel,
        snapshot: SnapshotModel,
        *,
        run_version_override: int | None = None,
    ) -> dict[str, Any]:
        gir_model, _ = await cls._current_gir(db, run.id)
        generation_result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run.id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        generation = generation_result.scalar_one_or_none()
        if generation is None:
            raise ValidationError("Generation evidence is missing.")
        variants_result = await db.execute(
            select(GuidanceVariantModel)
            .where(
                GuidanceVariantModel.generation_run_id == generation.id,
                GuidanceVariantModel.is_current.is_(True),
            )
            .order_by(
                GuidanceVariantModel.language,
                GuidanceVariantModel.channel,
            )
        )
        variants = list(variants_result.scalars().all())
        if len(variants) != 6:
            raise ValidationError("Exactly six current public variants are required.")
        semantic_items = []
        for variant in variants:
            compiled_result = await db.execute(
                select(CompilerResultModel)
                .where(CompilerResultModel.variant_id == variant.id)
                .order_by(CompilerResultModel.id.desc())
                .limit(1)
            )
            compiled = compiled_result.scalar_one_or_none()
            if compiled is None:
                raise ValidationError("Compiler evidence is missing.")
            comparison_result = await db.execute(
                select(SemanticComparisonModel)
                .where(SemanticComparisonModel.compiler_result_id == compiled.id)
                .order_by(SemanticComparisonModel.id.desc())
                .limit(1)
            )
            comparison = comparison_result.scalar_one_or_none()
            if comparison is None or not comparison.is_equivalent:
                raise ValidationError("Current semantic evidence is not equivalent.")
            semantic_items.append(
                {
                    "language": variant.language,
                    "channel": variant.channel,
                    "variant_id": str(variant.id),
                    "result_hash": comparison.result_hash,
                }
            )
        diagnostics_result = await db.execute(
            select(DiagnosticModel).where(
                DiagnosticModel.generation_run_id == generation.id
            )
        )
        diagnostics = list(diagnostics_result.scalars().all())
        unresolved = [item for item in diagnostics if item.blocking]
        if unresolved:
            raise ValidationError("Unresolved blocking diagnostics prevent approval.")
        simulation_result = await db.execute(
            select(SimulationRunModel)
            .where(SimulationRunModel.candidate_id == run.selected_candidate_id)
            .order_by(SimulationRunModel.created_at.desc())
            .limit(1)
        )
        simulation = simulation_result.scalar_one_or_none()
        if simulation is None or simulation.verdict == "BLOCK":
            raise ValidationError("Passing simulation evidence is missing.")
        return {
            "hash_contract_version": "CROWDCUE_APPROVAL_BUNDLE_V1",
            "run_id": str(run.id),
            "run_version": (
                run.version_id if run_version_override is None else run_version_override
            ),
            "candidate_id": str(run.selected_candidate_id),
            "gir_hash": gir_model.content_hash,
            "snapshot_hash": snapshot.canonical_input_hash,
            "variant_hashes": sorted(
                [
                    {
                        "language": variant.language,
                        "channel": variant.channel,
                        "version": variant.version,
                        "hash": variant.content_hash,
                    }
                    for variant in variants
                ],
                key=lambda item: (item["language"], item["channel"]),
            ),
            "semantic_result_hash": domain_hash(
                "CROWDCUE_SEMANTIC_SET_V1",
                sorted(
                    semantic_items,
                    key=lambda item: (item["language"], item["channel"]),
                ),
            ),
            "diagnostic_set_hash": domain_hash(
                "CROWDCUE_DIAGNOSTIC_SET_V1",
                sorted(
                    [
                        {
                            "code": item.code,
                            "blocking": item.blocking,
                            "resolved": item.resolved_at is not None,
                            "variant_id": (
                                str(item.variant_id) if item.variant_id else None
                            ),
                        }
                        for item in diagnostics
                    ],
                    key=lambda item: (
                        item["code"],
                        item["variant_id"] or "",
                        item["blocking"],
                        item["resolved"],
                    ),
                ),
            ),
            "simulation_result_hash": simulation.result_hash,
            "reference_data_version": run.reference_data_version,
            "terminology_version": run.terminology_version,
            "compiler_version": run.compiler_version,
            "simulation_policy_version": run.simulation_policy_version,
        }

    @classmethod
    async def expected_bundle_hash(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> str | None:
        run, snapshot = await cls._owned_run(db, run_id, session_id)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.PREFLIGHT_PASSED:
            return None
        payload = await cls._bundle_payload(db, run, snapshot)
        return domain_hash("CROWDCUE_APPROVAL_BUNDLE_V1", payload)

    @classmethod
    async def approve(
        cls,
        db: AsyncSession,
        *,
        run_id: UUID,
        session_id: UUID,
        approved_by_user_id: UUID,
        approver_role: str,
        approval_note: str | None,
        expected_bundle_hash: str,
    ) -> dict[str, Any]:
        normalized_role = approver_role.strip().upper()
        if normalized_role not in {"OPERATOR", "SUPERVISOR", "ADMINISTRATOR"}:
            raise ValidationError("Approver role is not permitted.")
        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        current = LifecycleState(run.lifecycle_state)
        if not validate_transition(current, LifecycleState.APPROVED):
            raise TransitionError("Run is not eligible for approval.")
        payload = await cls._bundle_payload(db, run, snapshot)
        server_hash = domain_hash("CROWDCUE_APPROVAL_BUNDLE_V1", payload)
        if expected_bundle_hash != server_hash:
            raise TransitionError("Approval bundle hash is stale or invalid.")
        approval = ApprovalRecordModel(
            run_id=run.id,
            approved_by_user_id=approved_by_user_id,
            approver_role=normalized_role,
            run_version=run.version_id,
            bundle_hash=server_hash,
            notes=approval_note,
        )
        db.add(approval)
        run.decision_bundle_hash = server_hash
        _transition(run, LifecycleState.APPROVED)
        await _append_event(
            db,
            session_id=session_id,
            run_id=run_id,
            event_type="APPROVAL_RECORDED",
            payload={
                "from_state": current.value,
                "to_state": LifecycleState.APPROVED.value,
                "approved_by_user_id": str(approved_by_user_id),
                "approver_role": normalized_role,
                "decision_bundle_hash": server_hash,
            },
        )
        await db.commit()
        return {
            "run_id": run_id,
            "lifecycle_state": run.lifecycle_state,
            "decision_bundle_hash": server_hash,
            "approved_at": approval.approved_at.isoformat(),
        }

    @classmethod
    async def publish(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await cls._owned_run(db, run_id, session_id, lock=True)
        if LifecycleState(run.lifecycle_state) is not LifecycleState.APPROVED:
            raise TransitionError("Run is not eligible for publication.")
        approval_result = await db.execute(
            select(ApprovalRecordModel).where(ApprovalRecordModel.run_id == run.id)
        )
        approval = approval_result.scalar_one_or_none()
        if approval is None:
            raise ValidationError("Approval evidence is missing.")
        payload = await cls._bundle_payload(
            db, run, snapshot, run_version_override=approval.run_version
        )
        current_hash = domain_hash("CROWDCUE_APPROVAL_BUNDLE_V1", payload)
        if (
            run.decision_bundle_hash != current_hash
            or approval.bundle_hash != current_hash
        ):
            raise TransitionError("Approved evidence bundle is stale or invalid.")
        current = _transition(run, LifecycleState.PUBLISHING)
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
        variant_map = {(item.language, item.channel): item for item in variants}
        batch = PublicationBatchModel(run_id=run_id, status="PUBLISHING")
        db.add(batch)
        await db.flush()
        deliveries: list[PublicationDeliveryModel] = []
        for language in ("en", "es", "fr"):
            for surface, channel in (("FAN_APP", "fan_app"), ("PA", "pa")):
                variant = variant_map[(language, channel)]
                deliveries.append(
                    PublicationDeliveryModel(
                        batch_id=batch.id,
                        surface=surface,
                        language=language,
                        variant_id=variant.id,
                        status="DELIVERED",
                        delivered_at=datetime.now(timezone.utc),
                    )
                )
            signage_variant = variant_map[(language, "fan_app")]
            deliveries.append(
                PublicationDeliveryModel(
                    batch_id=batch.id,
                    surface="SIGNAGE",
                    language=language,
                    variant_id=signage_variant.id,
                    status="DELIVERED",
                    delivered_at=datetime.now(timezone.utc),
                )
            )
        deliveries.append(
            PublicationDeliveryModel(
                batch_id=batch.id,
                surface="VOLUNTEER_DEVICE",
                language="ops",
                variant_id=None,
                status="DELIVERED",
                delivered_at=datetime.now(timezone.utc),
            )
        )
        db.add_all(deliveries)
        batch.status = "PUBLISHED"
        batch.completed_at = datetime.now(timezone.utc)
        _transition(run, LifecycleState.PUBLISHED)
        db.add(
            ActiveInstructionModel(
                run_id=run.id,
                venue_id=snapshot.venue_id,
                audience_json={"source": "current_gir", "run_id": str(run.id)},
            )
        )
        await _append_event(
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
            "deliveries": [
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
            ],
        }

    @classmethod
    async def details(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        run, snapshot = await cls._owned_run(db, run_id, session_id)
        candidate_result = await db.execute(
            select(CandidateModel).where(CandidateModel.run_id == run_id)
        )
        candidates = list(candidate_result.scalars().all())
        candidate_ids = [item.id for item in candidates]
        rejection_result = (
            await db.execute(
                select(CandidateRejectionModel).where(
                    CandidateRejectionModel.candidate_id.in_(candidate_ids)
                )
            )
            if candidate_ids
            else None
        )
        rejections_by_candidate: dict[UUID, list[CandidateRejectionModel]] = {}
        if rejection_result is not None:
            for rejection in rejection_result.scalars().all():
                rejections_by_candidate.setdefault(rejection.candidate_id, []).append(
                    rejection
                )
        gir_result = await db.execute(
            select(GIRVersionModel)
            .where(
                GIRVersionModel.run_id == run_id, GIRVersionModel.is_current.is_(True)
            )
            .order_by(GIRVersionModel.version.desc())
            .limit(1)
        )
        gir = gir_result.scalar_one_or_none()
        generation_result = await db.execute(
            select(GenerationRun)
            .where(GenerationRun.preflight_run_id == run_id)
            .order_by(GenerationRun.started_at.desc())
            .limit(1)
        )
        generation = generation_result.scalar_one_or_none()
        variants: list[GuidanceVariantModel] = []
        diagnostics: list[DiagnosticModel] = []
        if generation:
            variants_result = await db.execute(
                select(GuidanceVariantModel).where(
                    GuidanceVariantModel.generation_run_id == generation.id,
                    GuidanceVariantModel.is_current.is_(True),
                )
            )
            variants = list(variants_result.scalars().all())
            diagnostics_result = await db.execute(
                select(DiagnosticModel).where(
                    DiagnosticModel.generation_run_id == generation.id
                )
            )
            diagnostics = list(diagnostics_result.scalars().all())
        simulation_result = await db.execute(
            select(SimulationRunModel)
            .where(SimulationRunModel.candidate_id == run.selected_candidate_id)
            .order_by(SimulationRunModel.created_at.desc())
            .limit(1)
        )
        simulation = simulation_result.scalar_one_or_none()
        approval_result = await db.execute(
            select(ApprovalRecordModel).where(ApprovalRecordModel.run_id == run_id)
        )
        approval = approval_result.scalar_one_or_none()
        publication_batch_result = await db.execute(
            select(PublicationBatchModel)
            .where(PublicationBatchModel.run_id == run_id)
            .order_by(PublicationBatchModel.started_at.desc())
            .limit(1)
        )
        publication_batch = publication_batch_result.scalar_one_or_none()
        publication_deliveries: list[PublicationDeliveryModel] = []
        if publication_batch is not None:
            delivery_result = await db.execute(
                select(PublicationDeliveryModel)
                .where(PublicationDeliveryModel.batch_id == publication_batch.id)
                .order_by(
                    PublicationDeliveryModel.surface,
                    PublicationDeliveryModel.language,
                )
            )
            publication_deliveries = list(delivery_result.scalars().all())
        expected_hash = await cls.expected_bundle_hash(
            db, run_id=run_id, session_id=session_id
        )
        return {
            "run_id": run.id,
            "session_id": snapshot.session_id,
            "scenario_key": snapshot.scenario_key,
            "lifecycle_state": run.lifecycle_state,
            "run_version": run.version_id,
            "selected_candidate_id": run.selected_candidate_id,
            "snapshot_hash": snapshot.canonical_input_hash,
            "gir": gir.gir_data if gir else None,
            "candidates": [
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
                        {
                            "reason_code": rejection.reason_code,
                            "message": rejection.message,
                            "affected_route_id": rejection.affected_route_id,
                            "affected_edge_key": rejection.affected_edge_key,
                            "affected_asset_key": rejection.affected_asset_key,
                        }
                        for rejection in rejections_by_candidate.get(item.id, [])
                    ],
                }
                for item in candidates
            ],
            "generation_provenance": generation.provenance if generation else None,
            "variants": [
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
            ],
            "diagnostics": [
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
            ],
            "simulation": simulation.metrics if simulation else None,
            "approval": (
                {
                    "approved_by_user_id": approval.approved_by_user_id,
                    "approver_role": approval.approver_role,
                    "run_version": approval.run_version,
                    "bundle_hash": approval.bundle_hash,
                    "approval_note": approval.notes,
                    "approved_at": approval.approved_at,
                }
                if approval
                else None
            ),
            "publication_batch": (
                {
                    "id": publication_batch.id,
                    "status": publication_batch.status,
                    "started_at": publication_batch.started_at,
                    "completed_at": publication_batch.completed_at,
                }
                if publication_batch
                else None
            ),
            "publication_deliveries": [
                {
                    "surface": item.surface,
                    "language": item.language,
                    "status": item.status,
                    "variant_id": item.variant_id,
                    "error_message": item.error_message,
                    "delivered_at": item.delivered_at,
                }
                for item in publication_deliveries
            ],
            "expected_bundle_hash": expected_hash,
            "decision_bundle_hash": run.decision_bundle_hash,
        }

    @staticmethod
    async def snapshot_details(
        db: AsyncSession, *, snapshot_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        snapshot = await db.get(SnapshotModel, snapshot_id)
        if snapshot is None:
            raise RunNotFoundError("Snapshot not found.")
        if snapshot.session_id != session_id:
            raise OwnershipError("Session does not own this snapshot.")
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

    @classmethod
    async def audit_timeline(
        cls, db: AsyncSession, *, run_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        await cls._owned_run(db, run_id, session_id)
        session_result = await db.execute(
            select(AuditEventModel)
            .where(AuditEventModel.session_id == session_id)
            .order_by(AuditEventModel.sequence_number)
        )
        session_events = list(session_result.scalars().all())
        events = [item for item in session_events if item.run_id == run_id]
        return {
            "run_id": run_id,
            "chain_scope": "session",
            "session_event_count": len(session_events),
            "chain_valid": AuditService.verify_chain(session_events),
            "events": [
                {
                    "id": item.id,
                    "sequence_number": item.sequence_number,
                    "event_type": item.event_type,
                    "payload": item.payload,
                    "created_at": item.created_at,
                    "previous_event_hash": item.previous_event_hash,
                    "event_hash": item.event_hash,
                }
                for item in events
            ],
        }
