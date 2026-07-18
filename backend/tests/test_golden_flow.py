from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.gir import (
    GIR,
    AudienceScope,
    Directive,
    DirectiveAction,
    FallbackPolicy,
)
from backend.app.domain.guidance import GuidanceChannel, Language
from backend.app.domain.workflow import (
    DirectiveStrength,
    LifecycleState,
    validate_transition,
)
from backend.app.services.golden_flow_service import GoldenFlowService
from backend.app.services.guidance.fallback_renderer import render_fallback_guidance
from backend.app.services.guidance.reverse_compiler import reverse_compile_guidance
from backend.app.services.guidance.semantic_analyser import analyze_semantic_equivalence
from backend.app.services.guidance.service import GuidanceService
from backend.app.services.guidance.targeted_repair import (
    repair_spanish_protection_clause,
)
from backend.app.services.simulation_service import SimulationService


def make_gir() -> GIR:
    now = datetime(2026, 7, 18, 14, 30, tzinfo=timezone.utc)
    return GIR(
        instruction_id=uuid4(),
        version=1,
        venue_id=uuid4(),
        session_id=uuid4(),
        intent_id=uuid4(),
        candidate_id=uuid4(),
        venue_state_snapshot_id=uuid4(),
        reference_data_version="v2.0.0",
        terminology_version="2.0.0",
        simulation_policy_version="2.0.0",
        intervention_policy_version="1.1.0",
        compiler_version="2.0.0",
        source_team="Venue Operations",
        audience=AudienceScope(
            sections=("114", "115", "116", "117"),
            approach_zones=("node-plaza-west",),
            cohort_id="general-cohort",
        ),
        directive=Directive(
            action=DirectiveAction.REDIRECT,
            strength=DirectiveStrength.RECOMMENDED,
        ),
        destination_id="node-gate-a",
        route=(
            "node-plaza-west",
            "node-corridor-west",
            "node-gate-a-queue",
            "node-gate-a",
        ),
        excluded_cohorts=("mobility-assistance-cohort",),
        protected_route_ids=("route-mobility-protected",),
        required_asset_ids=(),
        fallback=FallbackPolicy(
            action=DirectiveAction.REDIRECT,
            destination_id="node-gate-b",
        ),
        effective_time=now,
        expiry_time=now + timedelta(minutes=10),
        lifecycle_state=LifecycleState.CANDIDATE_SELECTED,
    )


def test_fallback_creates_exact_six_semantically_equivalent_variants() -> None:
    gir = make_gir()
    variants = render_fallback_guidance(gir)
    assert len(variants) == 6
    assert {(variant.language, variant.channel) for variant in variants} == {
        (language, channel) for language in Language for channel in GuidanceChannel
    }
    for variant in variants:
        meaning = reverse_compile_guidance(variant)
        assert analyze_semantic_equivalence(gir, meaning, variant) == []


@pytest.mark.asyncio
async def test_demo_fault_is_detected_and_targeted_repair_isolated() -> None:
    gir = make_gir()
    result = await GuidanceService().generate_and_verify_guidance(
        gir, enable_fault_injection=True
    )
    assert result.fallback_used is True
    assert [item.code for item in result.diagnostics] == ["PROTECTED_COHORT_OMITTED"]
    before = {
        (item.language.value, item.channel.value): item for item in result.variants
    }
    repaired, diagnostics = GuidanceService.repair_variant(result.variants, gir)
    assert diagnostics == []
    after = {(item.language.value, item.channel.value): item for item in repaired}
    for key, original in before.items():
        if key != ("es", "fan_app"):
            assert after[key].content_hash == original.content_hash
    repaired_es = after[("es", "fan_app")]
    original_es = before[("es", "fan_app")]
    assert repaired_es.version == 2
    assert repaired_es.audience_action == original_es.audience_action
    assert repaired_es.route_clause == original_es.route_clause
    assert repaired_es.fallback_clause == original_es.fallback_clause
    assert repaired_es.validity_clause == original_es.validity_clause
    assert repaired_es.optional_explanation == original_es.optional_explanation
    assert repaired_es.protection_clause != original_es.protection_clause


def test_targeted_repair_rejects_wrong_variant() -> None:
    variant = render_fallback_guidance(make_gir())[0]
    if variant.language is Language.ES and variant.channel is GuidanceChannel.FAN_APP:
        pytest.skip("Matrix ordering unexpectedly put the repair target first.")
    with pytest.raises(ValueError, match="only supports"):
        repair_spanish_protection_clause(variant, make_gir())


def test_paired_simulation_is_reproducible_and_protected_route_blocks() -> None:
    first = SimulationService.run_paired_simulation(
        "gate_convergence",
        "cand-west-gate-a",
        "route-west-gate-a",
        "general-cohort",
    )
    second = SimulationService.run_paired_simulation(
        "gate_convergence",
        "cand-west-gate-a",
        "route-west-gate-a",
        "general-cohort",
    )
    assert first == second
    assert first["sample_count"] == 200
    assert first["paired"] is True
    assert first["verdict"] == "PASS"
    blocked = SimulationService.run_paired_simulation(
        "gate_convergence",
        "cand-protected",
        "route-mobility-protected",
        "general-cohort",
    )
    assert blocked["verdict"] == "BLOCK"
    assert blocked["protected_route_violations"] == 200


@pytest.mark.parametrize(
    ("scenario_key", "candidate_key", "route_key", "cohort_id", "verdict"),
    [
        (
            "gate_convergence",
            "cand-west-gate-a",
            "route-west-gate-a",
            "general-cohort",
            "PASS",
        ),
        (
            "transit_burst",
            "cand-transit-gate-b",
            "route-transit-gate-b",
            "general-cohort",
            "REVIEW",
        ),
        (
            "lift_outage",
            "cand-lift-outage-mobility-ok",
            "route-mobility-protected",
            "mobility-assistance-cohort",
            "REVIEW",
        ),
    ],
)
def test_simulation_uses_versioned_scenario_specific_profiles(
    scenario_key: str,
    candidate_key: str,
    route_key: str,
    cohort_id: str,
    verdict: str,
) -> None:
    result = SimulationService.run_paired_simulation(
        scenario_key, candidate_key, route_key, cohort_id
    )
    assert result["policy_version"] == SimulationService.policy_version()
    assert result["sample_count"] == 200
    assert result["paired"] is True
    assert result["verdict"] == verdict
    assert result["intervention"] != result["baseline"]


def test_simulation_rejects_unknown_scenario() -> None:
    with pytest.raises(ValueError, match="Unknown simulation scenario"):
        SimulationService.run_paired_simulation(
            "unknown", "candidate", "route-west-gate-a", "general-cohort"
        )


def test_state_graph_supports_clean_and_repair_branches() -> None:
    assert validate_transition(
        LifecycleState.GUIDANCE_VERIFYING, LifecycleState.SEMANTIC_PASSED
    )
    assert validate_transition(
        LifecycleState.GUIDANCE_VERIFYING, LifecycleState.PREFLIGHT_BLOCKED
    )
    assert validate_transition(
        LifecycleState.PREFLIGHT_BLOCKED, LifecycleState.GUIDANCE_VERIFYING
    )
    assert validate_transition(
        LifecycleState.GUIDANCE_VERIFYING, LifecycleState.CANDIDATE_SELECTED
    )
    assert validate_transition(
        LifecycleState.SIMULATION_RUNNING, LifecycleState.PREFLIGHT_BLOCKED
    )
    assert not validate_transition(
        LifecycleState.PREFLIGHT_BLOCKED, LifecycleState.APPROVED
    )


async def create_gate_run(client: AsyncClient, session_id: UUID) -> dict[str, object]:
    response = await client.post(
        "/api/runs",
        json={"session_id": str(session_id), "scenario_key": "gate_convergence"},
    )
    assert response.status_code == 201, response.text
    return response.json()


class ExplodingGuidanceService:
    async def generate_and_verify_guidance(
        self, gir: GIR, *, enable_fault_injection: bool
    ) -> None:
        del gir, enable_fault_injection
        raise RuntimeError("synthetic unexpected generation failure")


@pytest.mark.asyncio
async def test_unexpected_generation_failure_restores_retryable_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    session_id = uuid4()
    created = await create_gate_run(client, session_id)
    candidate = next(
        item
        for item in created["candidates"]
        if item["candidate_key"] == "cand-west-gate-a"
    )
    selection = await client.post(
        f"/api/runs/{created['run_id']}/select-candidate",
        headers={"X-Session-ID": str(session_id)},
        json={"candidate_id": candidate["id"]},
    )
    assert selection.status_code == 200

    with pytest.raises(RuntimeError, match="synthetic unexpected"):
        await GoldenFlowService.generate_guidance(
            db_session,
            run_id=UUID(created["run_id"]),
            session_id=session_id,
            enable_fault_injection=False,
            guidance_service=ExplodingGuidanceService(),  # type: ignore[arg-type]
        )

    details = await client.get(
        f"/api/runs/{created['run_id']}",
        headers={"X-Session-ID": str(session_id)},
    )
    assert details.status_code == 200
    assert details.json()["lifecycle_state"] == "CANDIDATE_SELECTED"
    audit = await client.get(
        f"/api/runs/{created['run_id']}/audit",
        headers={"X-Session-ID": str(session_id)},
    )
    assert "GUIDANCE_GENERATION_FAILED" in {
        item["event_type"] for item in audit.json()["events"]
    }


@pytest.mark.asyncio
async def test_full_persistent_golden_flow(client: AsyncClient) -> None:
    session_id = uuid4()
    headers = {"X-Session-ID": str(session_id)}
    created = await create_gate_run(client, session_id)
    run_id = created["run_id"]
    candidate = next(
        item
        for item in created["candidates"]
        if item["candidate_key"] == "cand-west-gate-a"
    )

    selection = await client.post(
        f"/api/runs/{run_id}/select-candidate",
        headers=headers,
        json={"candidate_id": candidate["id"]},
    )
    assert selection.status_code == 200, selection.text

    blocked = await client.post(
        f"/api/runs/{run_id}/generate-guidance",
        headers=headers,
        json={"enable_fault_injection": True},
    )
    assert blocked.status_code == 200, blocked.text
    blocked_data = blocked.json()
    assert blocked_data["lifecycle_state"] == "PREFLIGHT_BLOCKED"
    assert len(blocked_data["variants"]) == 6
    assert blocked_data["diagnostics"][0]["code"] == "PROTECTED_COHORT_OMITTED"

    forbidden_approval = await client.post(
        f"/api/runs/{run_id}/approve",
        headers=headers,
        json={
            "approved_by_user_id": str(uuid4()),
            "approver_role": "OPERATOR",
            "expected_bundle_hash": "0" * 64,
        },
    )
    assert forbidden_approval.status_code == 409

    repair = await client.post(f"/api/runs/{run_id}/repair", headers=headers)
    assert repair.status_code == 200, repair.text
    repair_data = repair.json()
    assert repair_data["lifecycle_state"] == "SEMANTIC_PASSED"
    assert repair_data["repaired_variant"]["version"] == 2
    assert len(repair_data["unaffected_variant_hashes"]) == 5
    assert repair_data["unaffected_spanish_clauses_unchanged"] is True

    simulation = await client.post(f"/api/runs/{run_id}/simulate", headers=headers)
    assert simulation.status_code == 200, simulation.text
    assert simulation.json()["simulation"]["verdict"] == "PASS"

    details = await client.get(f"/api/runs/{run_id}", headers=headers)
    assert details.status_code == 200, details.text
    details_data = details.json()
    assert details_data["lifecycle_state"] == "PREFLIGHT_PASSED"
    bundle_hash = details_data["expected_bundle_hash"]
    assert isinstance(bundle_hash, str) and len(bundle_hash) == 64
    repeated_details = await client.get(f"/api/runs/{run_id}", headers=headers)
    assert repeated_details.status_code == 200
    assert repeated_details.json()["expected_bundle_hash"] == bundle_hash

    stale = await client.post(
        f"/api/runs/{run_id}/approve",
        headers=headers,
        json={
            "approved_by_user_id": str(uuid4()),
            "approver_role": "OPERATOR",
            "expected_bundle_hash": "f" * 64,
        },
    )
    assert stale.status_code == 409

    approval = await client.post(
        f"/api/runs/{run_id}/approve",
        headers=headers,
        json={
            "approved_by_user_id": str(uuid4()),
            "approver_role": "SUPERVISOR",
            "approval_note": "Synthetic demo evidence reviewed.",
            "expected_bundle_hash": bundle_hash,
        },
    )
    assert approval.status_code == 201, approval.text
    assert approval.json()["lifecycle_state"] == "APPROVED"

    publication = await client.post(f"/api/runs/{run_id}/publish", headers=headers)
    assert publication.status_code == 202, publication.text
    publication_data = publication.json()
    assert publication_data["lifecycle_state"] == "PUBLISHED"
    assert publication_data["simulated"] is True
    assert len(publication_data["deliveries"]) == 10

    persisted = await client.get(f"/api/runs/{run_id}", headers=headers)
    assert persisted.status_code == 200, persisted.text
    persisted_data = persisted.json()
    assert persisted_data["approval"]["approver_role"] == "SUPERVISOR"
    assert persisted_data["publication_batch"]["status"] == "PUBLISHED"
    assert len(persisted_data["publication_deliveries"]) == 10
    assert all(
        item["status"] == "DELIVERED"
        for item in persisted_data["publication_deliveries"]
    )

    audit = await client.get(f"/api/runs/{run_id}/audit", headers=headers)
    assert audit.status_code == 200, audit.text
    audit_data = audit.json()
    assert audit_data["chain_valid"] is True
    event_types = [item["event_type"] for item in audit_data["events"]]
    assert "DEMO_FAULT_INJECTED" in event_types
    assert "TARGETED_REPAIR_COMPLETED" in event_types
    assert "PUBLICATION_COMPLETED" in event_types


@pytest.mark.asyncio
async def test_session_ownership_is_enforced(client: AsyncClient) -> None:
    owner = uuid4()
    created = await create_gate_run(client, owner)
    intruder_headers = {"X-Session-ID": str(uuid4())}
    response = await client.get(
        f"/api/runs/{created['run_id']}", headers=intruder_headers
    )
    assert response.status_code == 403


async def test_run_audit_uses_the_complete_session_chain(client: AsyncClient) -> None:
    session_id = uuid4()
    first = await client.post(
        "/api/runs",
        json={"session_id": str(session_id), "scenario_key": "gate_convergence"},
    )
    second = await client.post(
        "/api/runs",
        json={"session_id": str(session_id), "scenario_key": "lift_outage"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = await client.get(
        f"/api/runs/{second.json()['run_id']}/audit",
        headers={"X-Session-ID": str(session_id)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["chain_scope"] == "session"
    assert payload["chain_valid"] is True
    assert payload["session_event_count"] == 2
    assert len(payload["events"]) == 1
    assert payload["events"][0]["sequence_number"] == 1


@pytest.mark.parametrize(
    ("field", "replacement", "expected_code"),
    [
        (
            "audience_action",
            "Sections 114–116 approaching from West Plaza should redirect to Gate A.",
            "AUDIENCE_SCOPE_MISMATCH",
        ),
        (
            "route_clause",
            "Use the controlled route node-plaza-west node-gate-d.",
            "ROUTE_DRIFT",
        ),
        (
            "optional_explanation",
            "Proceed to Gate D.",
            "UNAUTHORIZED_DESTINATION_ADDED",
        ),
        (
            "optional_explanation",
            "Gate D is closed.",
            "UNAUTHORIZED_CLOSURE_CLAIM",
        ),
        (
            "optional_explanation",
            "Wait at Gate A.",
            "UNAUTHORIZED_WAITING_INSTRUCTION",
        ),
        (
            "optional_explanation",
            "Expected compliance is 80%.",
            "UNSUPPORTED_NUMERIC_CLAIM",
        ),
        (
            "optional_explanation",
            "Do not use Gate A.",
            "NEGATION_INVERSION",
        ),
    ],
)
def test_semantic_mutations_are_blocked(
    field: str, replacement: str, expected_code: str
) -> None:
    gir = make_gir()
    original = next(
        item
        for item in render_fallback_guidance(gir)
        if item.language is Language.EN and item.channel is GuidanceChannel.FAN_APP
    )
    clauses = {
        "audience_action": original.audience_action,
        "route_clause": original.route_clause,
        "fallback_clause": original.fallback_clause,
        "protection_clause": original.protection_clause,
        "validity_clause": original.validity_clause,
        "optional_explanation": original.optional_explanation or "",
    }
    clauses[field] = replacement
    from backend.app.services.guidance.fallback_renderer import build_variant

    mutated = build_variant(gir, original.language, original.channel, clauses)
    diagnostics = analyze_semantic_equivalence(
        gir, reverse_compile_guidance(mutated), mutated
    )
    assert expected_code in {item.code for item in diagnostics}
    assert all(item.blocking for item in diagnostics)
