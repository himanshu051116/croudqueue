import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.persistence.types import JSON_DOCUMENT


class ReferenceDataVersion(Base):
    __tablename__ = "reference_data_versions"

    version_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ref_version: Mapped[str] = mapped_column(
        String(50), ForeignKey("reference_data_versions.version_key"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    nodes = relationship(
        "VenueNode", back_populates="venue", cascade="all, delete-orphan"
    )
    edges = relationship(
        "VenueEdge", back_populates="venue", cascade="all, delete-orphan"
    )
    assets = relationship(
        "VenueAsset", back_populates="venue", cascade="all, delete-orphan"
    )


class VenueNode(Base):
    __tablename__ = "venue_nodes"
    __table_args__ = (
        UniqueConstraint("venue_id", "stable_key", name="uq_venue_node_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # GATE, arrival, section
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_key: Mapped[str] = mapped_column(String(100), nullable=False)

    venue = relationship("Venue", back_populates="nodes")


class VenueEdge(Base):
    __tablename__ = "venue_edges"
    __table_args__ = (
        UniqueConstraint("venue_id", "stable_key", name="uq_venue_edge_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue_nodes.id"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue_nodes.id"), nullable=False
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_key: Mapped[str] = mapped_column(String(100), nullable=False)

    venue = relationship("Venue", back_populates="edges")


class VenueAsset(Base):
    __tablename__ = "venue_assets"
    __table_args__ = (
        UniqueConstraint("venue_id", "stable_key", name="uq_venue_asset_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # LIFT, ESCALATOR
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # OPERATIONAL, OFFLINE
    stable_key: Mapped[str] = mapped_column(String(100), nullable=False)

    venue = relationship("Venue", back_populates="assets")


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("venue_id", "stable_key", name="uq_venue_route_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"), nullable=False)
    waypoints: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )  # list of node keys
    stable_key: Mapped[str] = mapped_column(String(100), nullable=False)
