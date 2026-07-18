"""Scope topology stable keys to their venue.

Revision ID: 003_venue_scoped_keys
Revises: 002_golden_flow_hardening
"""

from alembic import op

revision = "003_venue_scoped_keys"
down_revision = "002_golden_flow_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("venue_nodes", "venue_edges", "venue_assets", "routes"):
        op.drop_constraint(f"{table}_stable_key_key", table, type_="unique")
    op.create_unique_constraint(
        "uq_venue_node_key", "venue_nodes", ["venue_id", "stable_key"]
    )
    op.create_unique_constraint(
        "uq_venue_edge_key", "venue_edges", ["venue_id", "stable_key"]
    )
    op.create_unique_constraint(
        "uq_venue_asset_key", "venue_assets", ["venue_id", "stable_key"]
    )
    op.create_unique_constraint(
        "uq_venue_route_key", "routes", ["venue_id", "stable_key"]
    )


def downgrade() -> None:
    for name, table in (
        ("uq_venue_node_key", "venue_nodes"),
        ("uq_venue_edge_key", "venue_edges"),
        ("uq_venue_asset_key", "venue_assets"),
        ("uq_venue_route_key", "routes"),
    ):
        op.drop_constraint(name, table, type_="unique")
    for table in ("venue_nodes", "venue_edges", "venue_assets", "routes"):
        op.create_unique_constraint(f"{table}_stable_key_key", table, ["stable_key"])
