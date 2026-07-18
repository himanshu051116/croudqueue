from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.venue import (
    ReferenceDataVersion,
    Route,
    Venue,
    VenueAsset,
    VenueEdge,
    VenueNode,
)
from backend.app.services.integrity import domain_hash
from backend.app.services.venue_service import VenueService

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "reference_data"


class ReferenceDataIntegrityError(RuntimeError):
    """Raised when immutable reference data changes without a new version key."""


class ReferenceDataService:
    REQUIRED_FILES = (
        "diagnostics.json",
        "interventions.json",
        "routes.json",
        "scenarios.json",
        "simulation_policy.json",
        "terminology.json",
        "venue.json",
    )

    @staticmethod
    def deployed_reference_hash() -> str:
        """Read every required runtime JSON file and return one stable digest."""

        return domain_hash(
            "CROWDCUE_DEPLOYED_REFERENCE_DATA_V1",
            {
                name: (REFERENCE_DIR / name).read_text("utf-8")
                for name in ReferenceDataService.REQUIRED_FILES
            },
        )

    @staticmethod
    async def ensure_seeded(session: AsyncSession) -> Venue:
        topology = VenueService.load_topology()
        reference_hash = domain_hash(
            "CROWDCUE_REFERENCE_DATA_V1",
            {
                "venue": (REFERENCE_DIR / "venue.json").read_text("utf-8"),
                "routes": (REFERENCE_DIR / "routes.json").read_text("utf-8"),
                "scenarios": (REFERENCE_DIR / "scenarios.json").read_text("utf-8"),
                "terminology": (REFERENCE_DIR / "terminology.json").read_text("utf-8"),
            },
        )
        reference = await session.get(ReferenceDataVersion, topology.reference_version)
        if reference is None:
            session.add(
                ReferenceDataVersion(
                    version_key=topology.reference_version,
                    hash=reference_hash,
                )
            )
        elif reference.hash != reference_hash:
            raise ReferenceDataIntegrityError(
                "Reference data content changed without a new reference version."
            )

        result = await session.execute(
            select(Venue).where(Venue.id == topology.venue_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        venue = Venue(
            id=topology.venue_id,
            name=topology.name,
            ref_version=topology.reference_version,
        )
        session.add(venue)
        await session.flush()
        for node in topology.nodes.values():
            session.add(
                VenueNode(
                    id=node.id,
                    venue_id=topology.venue_id,
                    name=node.name,
                    node_type=node.node_type,
                    capacity=node.capacity,
                    stable_key=node.stable_key,
                )
            )
        # No ORM relationship orders these inserts; persist node FK targets before
        # PostgreSQL validates the edge batch below.
        await session.flush()
        for edge in topology.edges.values():
            session.add(
                VenueEdge(
                    id=edge.id,
                    venue_id=topology.venue_id,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    capacity=edge.capacity,
                    travel_time_seconds=edge.travel_time_seconds,
                    stable_key=edge.stable_key,
                )
            )
        for asset in topology.assets.values():
            session.add(
                VenueAsset(
                    id=asset.id,
                    venue_id=topology.venue_id,
                    asset_type=asset.asset_type,
                    status=asset.status,
                    stable_key=asset.stable_key,
                )
            )
        for route in topology.routes.values():
            session.add(
                Route(
                    id=route.id,
                    venue_id=topology.venue_id,
                    waypoints=list(route.waypoints),
                    stable_key=route.stable_key,
                )
            )
        await session.flush()
        return venue
