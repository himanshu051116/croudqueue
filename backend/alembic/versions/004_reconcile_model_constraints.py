"""Reconcile persisted constraints with the authoritative ORM models.

Revision ID: 004_reconcile_model_constraints
Revises: 003_venue_scoped_keys
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "004_reconcile_model_constraints"
down_revision = "003_venue_scoped_keys"
branch_labels = None
depends_on = None


REQUIRED_COLUMNS = (
    ("diagnostics", "details", postgresql.JSONB()),
    ("generation_runs", "status", sa.String(50)),
    ("generation_runs", "provenance", postgresql.JSONB()),
    ("intervention_candidates", "cohort_id", sa.String(100)),
    ("operational_intents", "objective", sa.String(100)),
    ("operational_intents", "target", sa.String(100)),
    ("operational_intents", "affected_audience", sa.String(150)),
    ("operational_intents", "constraints", postgresql.JSONB()),
    ("operational_intents", "excluded_cohorts", postgresql.JSONB()),
    ("preflight_runs", "venue_state_snapshot_id", sa.Uuid()),
    ("preflight_runs", "reference_data_version", sa.String(50)),
    ("preflight_runs", "terminology_version", sa.String(50)),
    ("preflight_runs", "simulation_policy_version", sa.String(50)),
    ("preflight_runs", "intervention_policy_version", sa.String(50)),
    ("preflight_runs", "compiler_version", sa.String(50)),
    ("preflight_runs", "fallback_template_version", sa.String(50)),
    ("preflight_runs", "sample_set_version", sa.String(50)),
    ("publication_deliveries", "language", sa.String(10)),
    ("semantic_comparisons", "result_hash", sa.String(64)),
    ("simulation_runs", "sample_set_id", sa.String(160)),
    ("simulation_runs", "seed", sa.Integer()),
    ("simulation_runs", "verdict", sa.String(20)),
    ("simulation_runs", "result_hash", sa.String(64)),
    ("simulation_runs", "metrics", postgresql.JSONB()),
    ("venue_state_snapshots", "venue_id", sa.Uuid()),
    ("venue_state_snapshots", "scenario_key", sa.String(100)),
    ("venue_state_snapshots", "reference_data_version", sa.String(50)),
    ("venue_state_snapshots", "canonical_input_hash", sa.String(64)),
)

REMOVED_SERVER_DEFAULTS = (
    ("generation_runs", "request_count", sa.Integer(), sa.text("0")),
    ("generation_runs", "successful_request_count", sa.Integer(), sa.text("0")),
    ("intervention_candidates", "selected", sa.Boolean(), sa.false()),
)


def upgrade() -> None:
    for table, column, column_type in REQUIRED_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=column_type,
            existing_nullable=True,
            nullable=False,
        )
    for table, column, column_type, _ in REMOVED_SERVER_DEFAULTS:
        op.alter_column(
            table,
            column,
            existing_type=column_type,
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    for table, column, column_type, default in REMOVED_SERVER_DEFAULTS:
        op.alter_column(
            table,
            column,
            existing_type=column_type,
            existing_nullable=False,
            server_default=default,
        )
    for table, column, column_type in reversed(REQUIRED_COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=column_type,
            existing_nullable=False,
            nullable=True,
        )
