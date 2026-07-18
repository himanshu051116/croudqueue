from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VenueId = UUID
NodeId = UUID
EdgeId = UUID
AssetId = UUID
RouteId = UUID


class Node(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: NodeId
    name: str
    node_type: str
    capacity: int = Field(gt=0)
    stable_key: str
    x: float = 0.0
    y: float = 0.0


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: EdgeId
    venue_id: VenueId
    source_id: NodeId
    target_id: NodeId
    capacity: int = Field(gt=0)
    travel_time_seconds: int = Field(gt=0)
    stable_key: str
    is_active: bool = True
    protected: bool = False


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: AssetId
    venue_id: VenueId
    asset_type: str
    status: str
    stable_key: str


class Route(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: RouteId
    venue_id: VenueId
    waypoints: tuple[str, ...]
    stable_key: str
    protected: bool = False
    required_assets: tuple[str, ...] = ()


class VenueTopology(BaseModel):
    model_config = ConfigDict(frozen=True)

    venue_id: VenueId
    name: str
    reference_version: str
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: dict[str, Edge] = Field(default_factory=dict)
    assets: dict[str, Asset] = Field(default_factory=dict)
    routes: dict[str, Route] = Field(default_factory=dict)

    def edge_between(self, source_key: str, target_key: str) -> Edge | None:
        source = self.nodes.get(source_key)
        target = self.nodes.get(target_key)
        if not source or not target:
            return None
        for edge in self.edges.values():
            if edge.source_id == source.id and edge.target_id == target.id:
                return edge
        return None

    def validate_topology(self) -> None:
        node_ids = {node.id for node in self.nodes.values()}
        for edge_key, edge in self.edges.items():
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError(f"Edge '{edge_key}' references an unknown node.")
        for route_key, route in self.routes.items():
            if len(route.waypoints) < 2:
                raise ValueError(
                    f"Route '{route_key}' requires at least two waypoints."
                )
            for waypoint in route.waypoints:
                if waypoint not in self.nodes:
                    raise ValueError(
                        f"Route '{route_key}' references unknown waypoint '{waypoint}'."
                    )
            for source, target in zip(route.waypoints, route.waypoints[1:]):
                if self.edge_between(source, target) is None:
                    raise ValueError(
                        f"Route '{route_key}' is discontinuous between "
                        f"'{source}' and '{target}'."
                    )
            for asset_key in route.required_assets:
                if asset_key not in self.assets:
                    raise ValueError(
                        f"Route '{route_key}' requires unknown asset '{asset_key}'."
                    )
