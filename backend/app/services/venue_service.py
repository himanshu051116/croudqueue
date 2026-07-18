from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

from backend.app.domain.candidate import (
    InterventionCandidate,
    OperationalIntentDomain,
)
from backend.app.domain.snapshot import VenueStateSnapshot
from backend.app.domain.venue import Asset, Edge, Node, Route, VenueTopology
from backend.app.services.integrity import domain_hash

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "reference_data"


class VenueService:
    _cached_topology: VenueTopology | None = None

    @classmethod
    def clear_cache(cls) -> None:
        cls._cached_topology = None

    @classmethod
    def load_topology(cls) -> VenueTopology:
        if cls._cached_topology is not None:
            return cls._cached_topology
        venue_data = json.loads((REFERENCE_DIR / "venue.json").read_text("utf-8"))
        routes_data = json.loads((REFERENCE_DIR / "routes.json").read_text("utf-8"))
        venue_id = uuid5(NAMESPACE_DNS, venue_data["venue_name"])
        nodes = {
            item["stable_key"]: Node(
                id=uuid5(venue_id, item["stable_key"]),
                name=item["name"],
                node_type=item["node_type"],
                capacity=item["capacity"],
                stable_key=item["stable_key"],
                x=item.get("x", 0.0),
                y=item.get("y", 0.0),
            )
            for item in venue_data["nodes"]
        }
        edges = {
            item["stable_key"]: Edge(
                id=uuid5(venue_id, item["stable_key"]),
                venue_id=venue_id,
                source_id=nodes[item["source_key"]].id,
                target_id=nodes[item["target_key"]].id,
                capacity=item["capacity"],
                travel_time_seconds=item["travel_time_seconds"],
                stable_key=item["stable_key"],
                is_active=item.get("is_active", True),
                protected=item.get("protected", False),
            )
            for item in venue_data["edges"]
        }
        assets = {
            item["stable_key"]: Asset(
                id=uuid5(venue_id, item["stable_key"]),
                venue_id=venue_id,
                asset_type=item["asset_type"],
                status=item["status"],
                stable_key=item["stable_key"],
            )
            for item in venue_data["assets"]
        }
        routes = {
            item["stable_key"]: Route(
                id=uuid5(venue_id, item["stable_key"]),
                venue_id=venue_id,
                waypoints=tuple(item["waypoints"]),
                stable_key=item["stable_key"],
                protected=item.get("protected", False),
                required_assets=tuple(item.get("required_assets", [])),
            )
            for item in routes_data["routes"]
        }
        topology = VenueTopology(
            venue_id=venue_id,
            name=venue_data["venue_name"],
            reference_version=venue_data["ref_version"],
            nodes=nodes,
            edges=edges,
            assets=assets,
            routes=routes,
        )
        topology.validate_topology()
        cls._cached_topology = topology
        return topology

    @classmethod
    def load_scenarios(cls) -> list[dict[str, Any]]:
        data = json.loads((REFERENCE_DIR / "scenarios.json").read_text("utf-8"))
        return list(data["scenarios"])

    @classmethod
    def get_scenario(cls, scenario_key: str) -> dict[str, Any]:
        for scenario in cls.load_scenarios():
            if scenario["key"] == scenario_key:
                return scenario
        raise ValueError(f"Unknown scenario '{scenario_key}'.")

    @classmethod
    def evaluate_preflight(
        cls,
        scenario_key: str,
        session_id: UUID,
        intent_override: OperationalIntentDomain | None = None,
        *,
        captured_at: datetime | None = None,
    ) -> tuple[
        VenueStateSnapshot,
        OperationalIntentDomain,
        list[InterventionCandidate],
    ]:
        topology = cls.load_topology()
        scenario = cls.get_scenario(scenario_key)
        nodes_state = {key: {"pressure": 0.0} for key in topology.nodes}
        edges_state = {key: {"is_active": True} for key in topology.edges}
        assets_state = {
            key: {"status": asset.status} for key, asset in topology.assets.items()
        }
        modifications = scenario.get("venue_state_modifications", {})
        for key, value in modifications.get("nodes", {}).items():
            nodes_state[key].update(value)
        for key, value in modifications.get("edges", {}).items():
            edges_state[key].update(value)
        for key, value in modifications.get("assets", {}).items():
            assets_state[key].update(value)

        default_intent = scenario["default_intent"]
        intent = intent_override or OperationalIntentDomain(
            objective=default_intent["objective"],
            target=default_intent["target"],
            affected_audience=default_intent["affected_audience"],
            constraints=default_intent.get("constraints", {}),
            excluded_cohorts=tuple(default_intent.get("excluded_cohorts", [])),
        )
        input_contract = {
            "venue_id": topology.venue_id,
            "scenario_key": scenario_key,
            "nodes_state": nodes_state,
            "edges_state": edges_state,
            "assets_state": assets_state,
            "intent": intent,
            "reference_data_version": topology.reference_version,
        }
        canonical_hash = domain_hash("CROWDCUE_SNAPSHOT_V1", input_contract)
        snapshot = VenueStateSnapshot(
            snapshot_id=uuid4(),
            session_id=session_id,
            timestamp=captured_at or datetime.now(timezone.utc),
            active_scenario_key=scenario_key,
            nodes_state=nodes_state,
            edges_state=edges_state,
            assets_state=assets_state,
            canonical_input_hash=canonical_hash,
        )

        policy = scenario.get("candidate_policy", {})
        rules = list(policy.get("rules", []))
        candidates: list[InterventionCandidate] = []
        for index, item in enumerate(policy.get("candidates", []), start=1):
            destination_key = item["destination_key"]
            route_key = item["route_key"]
            if (
                destination_key not in topology.nodes
                or route_key not in topology.routes
            ):
                raise ValueError(
                    f"Candidate '{item['candidate_key']}' references invalid topology."
                )
            candidate = InterventionCandidate(
                candidate_key=item["candidate_key"],
                title=item["title"],
                destination_id=topology.nodes[destination_key].id,
                route_id=topology.routes[route_key].id,
                cohort_id=item["cohort_id"],
                preliminary_rank=index,
                policy_version=policy.get("version", topology.reference_version),
            )
            candidate.evaluate_rules(
                topology,
                snapshot,
                intent,
                rules,
                item.get("active_edges_override"),
            )
            candidates.append(candidate)

        candidates.sort(
            key=lambda candidate: (
                not candidate.is_viable,
                candidate.preliminary_rank or 999,
                candidate.candidate_key,
            )
        )
        for rank, candidate in enumerate(candidates, start=1):
            candidate.preliminary_rank = rank
        return snapshot, intent, candidates

    @classmethod
    def candidate_config(cls, scenario_key: str, candidate_key: str) -> dict[str, Any]:
        scenario = cls.get_scenario(scenario_key)
        for candidate in scenario["candidate_policy"]["candidates"]:
            if candidate["candidate_key"] == candidate_key:
                return dict(candidate)
        raise ValueError(f"Unknown candidate '{candidate_key}'.")
