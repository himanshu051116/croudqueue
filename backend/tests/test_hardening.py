from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from backend.app.services.venue_service import VenueService


def test_generic_candidate_engine_accepts_new_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = {
        "key": "shuttle_surge",
        "name": "Shuttle surge",
        "description": "Synthetic surge",
        "venue_state_modifications": {},
        "default_intent": {
            "objective": "MANAGE_SURGE_FLOW",
            "target": "node-arrival-shuttle-blue",
            "affected_audience": "shuttle-flows",
            "constraints": {},
            "excluded_cohorts": [],
        },
        "candidate_policy": {
            "rules": ["ROUTE_CONTINUITY", "PROTECTED_ROUTE"],
            "candidates": [
                {
                    "candidate_key": "protected-general",
                    "title": "Protected route misuse",
                    "destination_key": "node-sections-100",
                    "route_key": "route-mobility-protected",
                    "cohort_id": "general-cohort",
                }
            ],
        },
    }
    monkeypatch.setattr(
        VenueService, "load_scenarios", staticmethod(lambda: [scenario])
    )
    snapshot, intent, candidates = VenueService.evaluate_preflight(
        "shuttle_surge", uuid4()
    )
    assert snapshot.active_scenario_key == "shuttle_surge"
    assert intent.objective == "MANAGE_SURGE_FLOW"
    assert [item.rejections[0].reason_code for item in candidates] == [
        "PROTECTED_ROUTE_VIOLATION"
    ]


def test_snapshot_and_candidate_output_are_reproducible() -> None:
    session_id = uuid4()
    first = VenueService.evaluate_preflight("gate_convergence", session_id)
    second = VenueService.evaluate_preflight("gate_convergence", session_id)
    assert first[0].canonical_input_hash == second[0].canonical_input_hash
    assert [
        (item.candidate_key, item.is_viable, item.preliminary_rank) for item in first[2]
    ] == [
        (item.candidate_key, item.is_viable, item.preliminary_rank)
        for item in second[2]
    ]


@pytest.mark.asyncio
async def test_compatibility_evaluate_and_session_ownership(
    client: AsyncClient,
) -> None:
    owner = uuid4()
    response = await client.post(
        "/api/venue/evaluate",
        json={"scenario_key": "gate_convergence", "session_id": str(owner)},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    allowed = await client.get(
        f"/api/venue/snapshot/{data['snapshot_id']}",
        headers={"X-Session-ID": str(owner)},
    )
    assert allowed.status_code == 200
    denied = await client.get(
        f"/api/venue/snapshot/{data['snapshot_id']}",
        headers={"X-Session-ID": str(uuid4())},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_api_error_statuses(client: AsyncClient) -> None:
    invalid = await client.post(
        "/api/runs",
        json={"session_id": str(uuid4()), "scenario_key": "not-a-scenario"},
    )
    assert invalid.status_code == 422
    malformed = await client.post("/api/runs", json={})
    assert malformed.status_code == 422
