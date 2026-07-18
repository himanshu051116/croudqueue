from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.snapshot import VenueStateSnapshot
from backend.app.domain.venue import VenueTopology


class CandidateRejection(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    reason_code: str
    message: str
    affected_route_id: UUID | None = None
    affected_edge_key: str | None = None
    affected_asset_key: str | None = None


class OperationalIntentDomain(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective: str
    target: str
    affected_audience: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    excluded_cohorts: tuple[str, ...] = ()


class InterventionCandidate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    candidate_key: str
    title: str
    destination_id: UUID
    route_id: UUID
    cohort_id: str
    is_viable: bool = True
    preliminary_rank: int | None = None
    policy_version: str | None = None
    selected: bool = False
    rejections: list[CandidateRejection] = Field(default_factory=list)

    def evaluate_rules(
        self,
        topology: VenueTopology,
        snapshot: VenueStateSnapshot,
        intent: OperationalIntentDomain,
        rules: list[str],
        active_edges_override: dict[str, bool] | None = None,
    ) -> None:
        self.rejections = []
        override = active_edges_override or {}
        route = next(
            (item for item in topology.routes.values() if item.id == self.route_id),
            None,
        )
        destination = next(
            (
                item
                for item in topology.nodes.values()
                if item.id == self.destination_id
            ),
            None,
        )
        if route is None:
            self.rejections.append(
                CandidateRejection(
                    reason_code="INVALID_ROUTE",
                    message="Candidate route does not exist in the venue topology.",
                )
            )
            self.is_viable = False
            return
        if destination is None:
            self.rejections.append(
                CandidateRejection(
                    reason_code="INVALID_DESTINATION",
                    message="Candidate destination does not exist in the venue topology.",
                )
            )
            self.is_viable = False
            return

        route_edges = []
        if "ROUTE_CONTINUITY" in rules:
            for source, target in zip(route.waypoints, route.waypoints[1:]):
                edge = topology.edge_between(source, target)
                if edge is None:
                    self.rejections.append(
                        CandidateRejection(
                            reason_code="DISCONTINUOUS_ROUTE",
                            message=(
                                f"Route is discontinuous between '{source}' and "
                                f"'{target}'."
                            ),
                            affected_route_id=route.id,
                        )
                    )
                else:
                    route_edges.append(edge)
        else:
            route_edges = [
                edge
                for source, target in zip(route.waypoints, route.waypoints[1:])
                if (edge := topology.edge_between(source, target)) is not None
            ]

        if "CLOSED_EDGE" in rules:
            for edge in route_edges:
                active = (
                    edge.is_active
                    and snapshot.edges_state.get(edge.stable_key, {}).get(
                        "is_active", True
                    )
                    and override.get(edge.stable_key, True)
                )
                if not active:
                    self.rejections.append(
                        CandidateRejection(
                            reason_code="CLOSED_EDGE_REJECT",
                            message=f"Route uses closed edge '{edge.stable_key}'.",
                            affected_route_id=route.id,
                            affected_edge_key=edge.stable_key,
                        )
                    )

        if "UNAVAILABLE_ASSET" in rules:
            offline = {
                key
                for key, value in snapshot.assets_state.items()
                if value.get("status") == "OFFLINE"
            }
            offline.update(intent.constraints.get("asset_offline", []))
            for asset_key in route.required_assets:
                if asset_key in offline:
                    self.rejections.append(
                        CandidateRejection(
                            reason_code="UNAVAILABLE_ASSET",
                            message=f"Route requires unavailable asset '{asset_key}'.",
                            affected_route_id=route.id,
                            affected_asset_key=asset_key,
                        )
                    )

        if "PROTECTED_ROUTE" in rules and route.protected:
            if self.cohort_id != "mobility-assistance-cohort":
                self.rejections.append(
                    CandidateRejection(
                        reason_code="PROTECTED_ROUTE_VIOLATION",
                        message=(
                            "Protected accessibility route is reserved for "
                            "mobility-assistance guests."
                        ),
                        affected_route_id=route.id,
                    )
                )

        if "CLOSED_DESTINATION" in rules:
            pressure_limit = float(intent.constraints.get("gate_pressure_limit", 0.9))
            pressure = float(
                snapshot.nodes_state.get(destination.stable_key, {}).get(
                    "pressure", 0.0
                )
            )
            if pressure >= pressure_limit:
                self.rejections.append(
                    CandidateRejection(
                        reason_code="CLOSED_DESTINATION",
                        message=(
                            f"Destination '{destination.stable_key}' exceeds the "
                            f"pressure policy threshold ({pressure:.0%})."
                        ),
                        affected_route_id=route.id,
                    )
                )

        self.is_viable = not self.rejections
