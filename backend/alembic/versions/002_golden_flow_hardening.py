"""Golden flow persistence hardening.

Revision ID: 002_golden_flow_hardening
Revises: 001_baseline
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "002_golden_flow_hardening"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "venue_state_snapshots", sa.Column("venue_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "venue_state_snapshots",
        sa.Column("scenario_key", sa.String(100), nullable=True),
    )
    op.add_column(
        "venue_state_snapshots",
        sa.Column("reference_data_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "venue_state_snapshots",
        sa.Column("canonical_input_hash", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_snapshot_venue", "venue_state_snapshots", "venues", ["venue_id"], ["id"]
    )

    op.add_column(
        "operational_intents", sa.Column("objective", sa.String(100), nullable=True)
    )
    op.add_column(
        "operational_intents", sa.Column("target", sa.String(100), nullable=True)
    )
    op.add_column(
        "operational_intents",
        sa.Column("affected_audience", sa.String(150), nullable=True),
    )
    op.add_column(
        "operational_intents",
        sa.Column("constraints", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "operational_intents",
        sa.Column("excluded_cohorts", postgresql.JSONB(), nullable=True),
    )

    op.add_column(
        "intervention_candidates", sa.Column("cohort_id", sa.String(100), nullable=True)
    )
    op.add_column(
        "intervention_candidates",
        sa.Column("preliminary_rank", sa.Integer(), nullable=True),
    )
    op.add_column(
        "intervention_candidates",
        sa.Column("policy_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "intervention_candidates",
        sa.Column("selected", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_run_candidate_key", "intervention_candidates", ["run_id", "candidate_key"]
    )

    op.add_column(
        "candidate_rejections", sa.Column("affected_route_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "candidate_rejections",
        sa.Column("affected_edge_key", sa.String(100), nullable=True),
    )
    op.add_column(
        "candidate_rejections",
        sa.Column("affected_asset_key", sa.String(100), nullable=True),
    )
    op.create_foreign_key(
        "fk_rejection_route",
        "candidate_rejections",
        "routes",
        ["affected_route_id"],
        ["id"],
    )

    op.create_table(
        "gir_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("instruction_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("gir_data", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["preflight_runs.id"]),
        sa.UniqueConstraint("run_id", "version", name="uq_gir_run_version"),
    )

    op.add_column("generation_runs", sa.Column("status", sa.String(50), nullable=True))
    op.add_column(
        "generation_runs",
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "generation_runs",
        sa.Column(
            "successful_request_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "generation_runs", sa.Column("safe_error_code", sa.String(100), nullable=True)
    )
    op.add_column(
        "generation_runs", sa.Column("request_id_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "generation_runs", sa.Column("provenance", postgresql.JSONB(), nullable=True)
    )

    op.create_unique_constraint(
        "uq_generation_variant_version",
        "guidance_variants",
        ["generation_run_id", "language", "channel", "version"],
    )

    op.add_column("diagnostics", sa.Column("variant_id", sa.Uuid(), nullable=True))
    op.add_column(
        "diagnostics", sa.Column("details", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "diagnostics",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_diagnostic_variant",
        "diagnostics",
        "guidance_variants",
        ["variant_id"],
        ["id"],
    )

    op.add_column(
        "semantic_comparisons", sa.Column("result_hash", sa.String(64), nullable=True)
    )

    op.add_column(
        "simulation_runs", sa.Column("sample_set_id", sa.String(160), nullable=True)
    )
    op.add_column("simulation_runs", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column("simulation_runs", sa.Column("verdict", sa.String(20), nullable=True))
    op.add_column(
        "simulation_runs", sa.Column("result_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "simulation_runs", sa.Column("metrics", postgresql.JSONB(), nullable=True)
    )

    op.create_unique_constraint("uq_approval_run", "approval_records", ["run_id"])
    op.add_column(
        "publication_batches",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("publication_deliveries", "channel", new_column_name="surface")
    op.add_column(
        "publication_deliveries", sa.Column("language", sa.String(10), nullable=True)
    )
    op.add_column(
        "publication_deliveries", sa.Column("variant_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_publication_variant",
        "publication_deliveries",
        "guidance_variants",
        ["variant_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_batch_surface_language",
        "publication_deliveries",
        ["batch_id", "surface", "language"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_batch_surface_language", "publication_deliveries", type_="unique"
    )
    op.drop_constraint(
        "fk_publication_variant", "publication_deliveries", type_="foreignkey"
    )
    op.drop_column("publication_deliveries", "variant_id")
    op.drop_column("publication_deliveries", "language")
    op.alter_column("publication_deliveries", "surface", new_column_name="channel")
    op.drop_column("publication_batches", "completed_at")
    op.drop_constraint("uq_approval_run", "approval_records", type_="unique")
    for column in ("metrics", "result_hash", "verdict", "seed", "sample_set_id"):
        op.drop_column("simulation_runs", column)
    op.drop_column("semantic_comparisons", "result_hash")
    op.drop_constraint("fk_diagnostic_variant", "diagnostics", type_="foreignkey")
    for column in ("resolved_at", "details", "variant_id"):
        op.drop_column("diagnostics", column)
    op.drop_constraint(
        "uq_generation_variant_version", "guidance_variants", type_="unique"
    )
    for column in (
        "provenance",
        "request_id_hash",
        "safe_error_code",
        "successful_request_count",
        "request_count",
        "status",
    ):
        op.drop_column("generation_runs", column)
    op.drop_table("gir_versions")
    op.drop_constraint("fk_rejection_route", "candidate_rejections", type_="foreignkey")
    for column in ("affected_asset_key", "affected_edge_key", "affected_route_id"):
        op.drop_column("candidate_rejections", column)
    op.drop_constraint(
        "uq_run_candidate_key", "intervention_candidates", type_="unique"
    )
    for column in ("selected", "policy_version", "preliminary_rank", "cohort_id"):
        op.drop_column("intervention_candidates", column)
    for column in (
        "excluded_cohorts",
        "constraints",
        "affected_audience",
        "target",
        "objective",
    ):
        op.drop_column("operational_intents", column)
    op.drop_constraint("fk_snapshot_venue", "venue_state_snapshots", type_="foreignkey")
    for column in (
        "canonical_input_hash",
        "reference_data_version",
        "scenario_key",
        "venue_id",
    ):
        op.drop_column("venue_state_snapshots", column)
