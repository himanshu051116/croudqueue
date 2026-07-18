from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.app.domain.candidate import InterventionCandidate, OperationalIntentDomain
from backend.app.domain.snapshot import VenueStateSnapshot
from backend.app.domain.venue import Route
from backend.app.services.venue_service import VenueService


def test_valid_topology_contains_complete_aurora_contract() -> None:
    topology = VenueService.load_topology()
    topology.validate_topology()
    required = {
        "node-gate-a",
        "node-gate-b",
        "node-gate-c",
        "node-gate-d",
        "node-plaza-north",
        "node-plaza-west",
        "node-plaza-east",
        "node-arrival-transit-red",
        "node-arrival-shuttle-blue",
    }
    assert required <= set(topology.nodes)
    assert "asset-lift-d2" in topology.assets


def test_invalid_edge_reference_fails_without_mutating_frozen_models() -> None:
    topology = VenueService.load_topology()
    key = "edge-west-plaza-to-corr-west"
    bad_edge = topology.edges[key].model_copy(update={"source_id": uuid4()})
    bad_edges = dict(topology.edges)
    bad_edges[key] = bad_edge
    invalid = topology.model_copy(update={"edges": bad_edges})
    with pytest.raises(ValueError, match="unknown node"):
        invalid.validate_topology()


def test_invalid_route_waypoint_fails() -> None:
    topology = VenueService.load_topology()
    key = "route-west-gate-a"
    bad_route = topology.routes[key].model_copy(
        update={"waypoints": topology.routes[key].waypoints + ("node-invalid",)}
    )
    routes = dict(topology.routes)
    routes[key] = bad_route
    invalid = topology.model_copy(update={"routes": routes})
    with pytest.raises(ValueError, match="unknown waypoint"):
        invalid.validate_topology()


def test_discontinuous_route_is_rejected() -> None:
    topology = VenueService.load_topology()
    invalid_route = Route(
        id=uuid4(),
        venue_id=topology.venue_id,
        waypoints=("node-plaza-west", "node-concourse-east"),
        stable_key="route-discontinuous",
    )
    routes = dict(topology.routes)
    routes[invalid_route.stable_key] = invalid_route
    topology = topology.model_copy(update={"routes": routes})
    candidate = InterventionCandidate(
        candidate_key="cand-discontinuous",
        title="Discontinuous",
        destination_id=topology.nodes["node-gate-a"].id,
        route_id=invalid_route.id,
        cohort_id="general-cohort",
    )
    snapshot = VenueStateSnapshot(
        snapshot_id=uuid4(),
        session_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        active_scenario_key="gate_convergence",
    )
    candidate.evaluate_rules(
        topology,
        snapshot,
        OperationalIntentDomain(
            objective="TEST", target="node-gate-c", affected_audience="general"
        ),
        ["ROUTE_CONTINUITY"],
    )
    assert {item.reason_code for item in candidate.rejections} == {
        "DISCONTINUOUS_ROUTE"
    }


@pytest.mark.parametrize(
    "scenario_key,viable,rejection_codes",
    [
        (
            "gate_convergence",
            {"cand-west-gate-a", "cand-west-gate-b", "cand-mobility-protected-a"},
            {"CLOSED_DESTINATION"},
        ),
        (
            "transit_burst",
            {"cand-transit-gate-b", "cand-transit-mobility"},
            {"CLOSED_EDGE_REJECT"},
        ),
        (
            "lift_outage",
            {"cand-lift-outage-mobility-ok"},
            {"UNAVAILABLE_ASSET", "PROTECTED_ROUTE_VIOLATION"},
        ),
    ],
)
def test_scenario_vetoes(
    scenario_key: str, viable: set[str], rejection_codes: set[str]
) -> None:
    _, _, candidates = VenueService.evaluate_preflight(scenario_key, uuid4())
    assert {item.candidate_key for item in candidates if item.is_viable} == viable
    actual_codes = {
        rejection.reason_code
        for candidate in candidates
        for rejection in candidate.rejections
    }
    assert rejection_codes <= actual_codes


def test_candidate_ordering_is_deterministic() -> None:
    session_id = uuid4()
    first = VenueService.evaluate_preflight("gate_convergence", session_id)[2]
    second = VenueService.evaluate_preflight("gate_convergence", session_id)[2]
    assert [
        (item.candidate_key, item.is_viable, item.preliminary_rank) for item in first
    ] == [
        (item.candidate_key, item.is_viable, item.preliminary_rank) for item in second
    ]
