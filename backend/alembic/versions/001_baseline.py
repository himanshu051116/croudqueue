"""baseline migration

Revision ID: 001_baseline
Revises:
Create Date: 2026-07-17 17:15:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Reference Data Version
    op.create_table(
        "reference_data_versions",
        sa.Column("version_key", sa.String(length=50), primary_key=True),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Venues
    op.create_table(
        "venues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("ref_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ref_version"], ["reference_data_versions.version_key"]
        ),
    )

    # 3. Venue Nodes
    op.create_table(
        "venue_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("stable_key", sa.String(length=100), unique=True, nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
    )

    # 4. Routes
    op.create_table(
        "routes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("waypoints", postgresql.JSONB(), nullable=False),
        sa.Column("stable_key", sa.String(length=100), unique=True, nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
    )

    # 5. Venue Edges
    op.create_table(
        "venue_edges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("travel_time_seconds", sa.Integer(), nullable=False),
        sa.Column("stable_key", sa.String(length=100), unique=True, nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["venue_nodes.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["venue_nodes.id"]),
    )

    # 6. Venue Assets
    op.create_table(
        "venue_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("stable_key", sa.String(length=100), unique=True, nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
    )

    # 7. Sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("active_scenario_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 8. Venue State Snapshot
    op.create_table(
        "venue_state_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nodes_state", postgresql.JSONB(), nullable=False),
        sa.Column("edges_state", postgresql.JSONB(), nullable=False),
        sa.Column("assets_state", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
    )

    # 9. Operational Intent
    op.create_table(
        "operational_intents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text", sa.TEXT(), nullable=False),
        sa.Column("interpreted_objective", sa.TEXT(), nullable=True),
        sa.Column("interpreted_constraints", postgresql.JSONB(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
    )

    # 10. Preflight Runs
    op.create_table(
        "preflight_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("selected_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("venue_state_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("decision_result_id", sa.Uuid(), nullable=True),
        sa.Column("reference_data_version", sa.String(length=50), nullable=True),
        sa.Column("terminology_version", sa.String(length=50), nullable=True),
        sa.Column("simulation_policy_version", sa.String(length=50), nullable=True),
        sa.Column("intervention_policy_version", sa.String(length=50), nullable=True),
        sa.Column("compiler_version", sa.String(length=50), nullable=True),
        sa.Column("fallback_template_version", sa.String(length=50), nullable=True),
        sa.Column("sample_set_version", sa.String(length=50), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=50), nullable=False),
        sa.Column("decision_bundle_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intent_id"], ["operational_intents.id"]),
        sa.ForeignKeyConstraint(
            ["venue_state_snapshot_id"], ["venue_state_snapshots.id"]
        ),
    )

    # 11. Intervention Candidates
    op.create_table(
        "intervention_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("destination_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("is_viable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["preflight_runs.id"]),
        sa.ForeignKeyConstraint(["destination_id"], ["venue_nodes.id"]),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"]),
    )

    # Add Alter constraints for circular relations in Preflight Runs
    op.create_foreign_key(
        "fk_preflight_selected_candidate",
        "preflight_runs",
        "intervention_candidates",
        ["selected_candidate_id"],
        ["id"],
        use_alter=True,
    )

    # 12. Candidate Rejection
    op.create_table(
        "candidate_rejections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("message", sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["intervention_candidates.id"]),
    )

    # 13. Generation Runs
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preflight_run_id", sa.Uuid(), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["preflight_run_id"], ["preflight_runs.id"]),
    )

    # 14. Guidance Variants
    op.create_table(
        "guidance_variants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("audience_action", sa.TEXT(), nullable=False),
        sa.Column("route_clause", sa.TEXT(), nullable=False),
        sa.Column("fallback_clause", sa.TEXT(), nullable=False),
        sa.Column("protection_clause", sa.TEXT(), nullable=False),
        sa.Column("validity_clause", sa.TEXT(), nullable=False),
        sa.Column("optional_explanation", sa.TEXT(), nullable=True),
        sa.Column("rendered_text", sa.TEXT(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"]),
    )

    # 15. Diagnostics
    op.create_table(
        "diagnostics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("message", sa.TEXT(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"]),
    )

    # 16. Repair Attempts
    op.create_table(
        "repair_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("diagnostic_id", sa.Uuid(), nullable=False),
        sa.Column("target_clause", sa.String(length=100), nullable=False),
        sa.Column("original_text", sa.TEXT(), nullable=False),
        sa.Column("repaired_text", sa.TEXT(), nullable=False),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["variant_id"], ["guidance_variants.id"]),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"]),
        sa.ForeignKeyConstraint(["diagnostic_id"], ["diagnostics.id"]),
    )

    # 17. Compiler Results
    op.create_table(
        "compiler_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("compiled_meaning", postgresql.JSONB(), nullable=False),
        sa.Column("compiler_version", sa.String(length=50), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["variant_id"], ["guidance_variants.id"]),
    )

    # 18. Semantic Comparisons
    op.create_table(
        "semantic_comparisons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("compiler_result_id", sa.Uuid(), nullable=False),
        sa.Column("differences", postgresql.JSONB(), nullable=False),
        sa.Column("is_equivalent", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["compiler_result_id"], ["compiler_results.id"]),
    )

    # 19. Simulation Runs
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("samples_count", sa.Integer(), nullable=False),
        sa.Column("failure_frequency", sa.Float(), nullable=False),
        sa.Column("wilson_lower", sa.Float(), nullable=False),
        sa.Column("wilson_upper", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["intervention_candidates.id"]),
    )

    # 20. Simulation Samples
    op.create_table(
        "simulation_samples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("simulation_run_id", sa.Uuid(), nullable=False),
        sa.Column("sample_key", sa.String(length=100), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
    )

    # 21. Simulation Traces
    op.create_table(
        "simulation_traces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("simulation_run_id", sa.Uuid(), nullable=False),
        sa.Column("time_series_data", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
    )

    # 22. Decision Results
    op.create_table(
        "decision_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preflight_run_id", sa.Uuid(), nullable=False),
        sa.Column("selected_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("ranking_order", postgresql.JSONB(), nullable=False),
        sa.Column("rank_vectors", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(["preflight_run_id"], ["preflight_runs.id"]),
        sa.ForeignKeyConstraint(
            ["selected_candidate_id"], ["intervention_candidates.id"]
        ),
    )

    # Add Alter constraints for Decision Result ID in Preflight Runs
    op.create_foreign_key(
        "fk_preflight_decision_result",
        "preflight_runs",
        "decision_results",
        ["decision_result_id"],
        ["id"],
        use_alter=True,
    )

    # 23. Approval Records
    op.create_table(
        "approval_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approver_role", sa.String(length=50), nullable=False),
        sa.Column("run_version", sa.Integer(), nullable=False),
        sa.Column("bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.TEXT(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["preflight_runs.id"]),
    )

    # 24. Publication Batches
    op.create_table(
        "publication_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["preflight_runs.id"]),
    )

    # 25. Publication Deliveries
    op.create_table(
        "publication_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["publication_batches.id"]),
    )

    # 26. Active Instructions
    op.create_table(
        "active_instructions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("audience_json", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["preflight_runs.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
    )

    # 27. Audit Events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["preflight_runs.id"]),
        sa.UniqueConstraint(
            "session_id", "sequence_number", name="uq_session_sequence"
        ),
    )

    # 28. Outbox Events
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("delivery_status", sa.String(length=50), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.Uuid(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 29. Idempotency Keys
    op.create_table(
        "idempotency_keys",
        sa.Column("key_hash", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("command_type", sa.String(length=100), nullable=False),
        sa.Column("resource_identifier", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("lock_acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    # Drop Alter Constraints first
    op.drop_constraint(
        "fk_preflight_selected_candidate", "preflight_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_preflight_decision_result", "preflight_runs", type_="foreignkey"
    )

    # Drop all tables in reverse dependency order
    op.drop_table("idempotency_keys")
    op.drop_table("outbox_events")
    op.drop_table("audit_events")
    op.drop_table("active_instructions")
    op.drop_table("publication_deliveries")
    op.drop_table("publication_batches")
    op.drop_table("approval_records")
    op.drop_table("decision_results")
    op.drop_table("simulation_traces")
    op.drop_table("simulation_samples")
    op.drop_table("simulation_runs")
    op.drop_table("semantic_comparisons")
    op.drop_table("compiler_results")
    op.drop_table("repair_attempts")
    op.drop_table("diagnostics")
    op.drop_table("guidance_variants")
    op.drop_table("generation_runs")
    op.drop_table("candidate_rejections")
    op.drop_table("intervention_candidates")
    op.drop_table("preflight_runs")
    op.drop_table("operational_intents")
    op.drop_table("venue_state_snapshots")
    op.drop_table("sessions")
    op.drop_table("venue_assets")
    sa.orm.session.close_all()
    op.drop_table("venue_edges")
    op.drop_table("routes")
    op.drop_table("venue_nodes")
    op.drop_table("venues")
    op.drop_table("reference_data_versions")
