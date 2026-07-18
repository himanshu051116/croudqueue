INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume transactional DDL.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INFO  [alembic.runtime.migration] Running upgrade  -> 001_baseline, baseline migration
-- Running upgrade  -> 001_baseline

CREATE TABLE reference_data_versions (
    version_key VARCHAR(50) NOT NULL, 
    hash VARCHAR(64) NOT NULL, 
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (version_key)
);

CREATE TABLE venues (
    id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    ref_version VARCHAR(50) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(ref_version) REFERENCES reference_data_versions (version_key)
);

CREATE TABLE venue_nodes (
    id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    node_type VARCHAR(50) NOT NULL, 
    capacity INTEGER NOT NULL, 
    stable_key VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(venue_id) REFERENCES venues (id), 
    UNIQUE (stable_key)
);

CREATE TABLE routes (
    id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    waypoints JSONB NOT NULL, 
    stable_key VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(venue_id) REFERENCES venues (id), 
    UNIQUE (stable_key)
);

CREATE TABLE venue_edges (
    id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    source_id UUID NOT NULL, 
    target_id UUID NOT NULL, 
    capacity INTEGER NOT NULL, 
    travel_time_seconds INTEGER NOT NULL, 
    stable_key VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(venue_id) REFERENCES venues (id), 
    FOREIGN KEY(source_id) REFERENCES venue_nodes (id), 
    FOREIGN KEY(target_id) REFERENCES venue_nodes (id), 
    UNIQUE (stable_key)
);

CREATE TABLE venue_assets (
    id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    asset_type VARCHAR(50) NOT NULL, 
    status VARCHAR(50) NOT NULL, 
    stable_key VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(venue_id) REFERENCES venues (id), 
    UNIQUE (stable_key)
);

CREATE TABLE sessions (
    id UUID NOT NULL, 
    active_scenario_key VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    ended_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE TABLE venue_state_snapshots (
    id UUID NOT NULL, 
    session_id UUID NOT NULL, 
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
    nodes_state JSONB NOT NULL, 
    edges_state JSONB NOT NULL, 
    assets_state JSONB NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id)
);

CREATE TABLE operational_intents (
    id UUID NOT NULL, 
    session_id UUID NOT NULL, 
    raw_text TEXT NOT NULL, 
    interpreted_objective TEXT, 
    interpreted_constraints JSONB, 
    confirmed BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id)
);

CREATE TABLE preflight_runs (
    id UUID NOT NULL, 
    version_id INTEGER NOT NULL, 
    intent_id UUID NOT NULL, 
    selected_candidate_id UUID, 
    venue_state_snapshot_id UUID, 
    decision_result_id UUID, 
    reference_data_version VARCHAR(50), 
    terminology_version VARCHAR(50), 
    simulation_policy_version VARCHAR(50), 
    intervention_policy_version VARCHAR(50), 
    compiler_version VARCHAR(50), 
    fallback_template_version VARCHAR(50), 
    sample_set_version VARCHAR(50), 
    lifecycle_state VARCHAR(50) NOT NULL, 
    decision_bundle_hash VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(intent_id) REFERENCES operational_intents (id), 
    FOREIGN KEY(venue_state_snapshot_id) REFERENCES venue_state_snapshots (id)
);

CREATE TABLE intervention_candidates (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    candidate_key VARCHAR(100) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    destination_id UUID NOT NULL, 
    route_id UUID NOT NULL, 
    is_viable BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES preflight_runs (id), 
    FOREIGN KEY(destination_id) REFERENCES venue_nodes (id), 
    FOREIGN KEY(route_id) REFERENCES routes (id)
);

ALTER TABLE preflight_runs ADD CONSTRAINT fk_preflight_selected_candidate FOREIGN KEY(selected_candidate_id) REFERENCES intervention_candidates (id);

CREATE TABLE candidate_rejections (
    id UUID NOT NULL, 
    candidate_id UUID NOT NULL, 
    reason_code VARCHAR(100) NOT NULL, 
    message TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES intervention_candidates (id)
);

CREATE TABLE generation_runs (
    id UUID NOT NULL, 
    preflight_run_id UUID NOT NULL, 
    model_used VARCHAR(100) NOT NULL, 
    provider VARCHAR(50) NOT NULL, 
    fallback_used BOOLEAN NOT NULL, 
    attempt_count INTEGER NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    latency_ms INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(preflight_run_id) REFERENCES preflight_runs (id)
);

CREATE TABLE guidance_variants (
    id UUID NOT NULL, 
    generation_run_id UUID NOT NULL, 
    language VARCHAR(10) NOT NULL, 
    channel VARCHAR(50) NOT NULL, 
    version INTEGER NOT NULL, 
    audience_action TEXT NOT NULL, 
    route_clause TEXT NOT NULL, 
    fallback_clause TEXT NOT NULL, 
    protection_clause TEXT NOT NULL, 
    validity_clause TEXT NOT NULL, 
    optional_explanation TEXT, 
    rendered_text TEXT NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    is_current BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE diagnostics (
    id UUID NOT NULL, 
    generation_run_id UUID NOT NULL, 
    stage VARCHAR(50) NOT NULL, 
    severity VARCHAR(50) NOT NULL, 
    code VARCHAR(100) NOT NULL, 
    message TEXT NOT NULL, 
    blocking BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE repair_attempts (
    id UUID NOT NULL, 
    variant_id UUID NOT NULL, 
    diagnostic_id UUID NOT NULL, 
    target_clause VARCHAR(100) NOT NULL, 
    original_text TEXT NOT NULL, 
    repaired_text TEXT NOT NULL, 
    generation_run_id UUID NOT NULL, 
    succeeded BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(variant_id) REFERENCES guidance_variants (id), 
    FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
    FOREIGN KEY(diagnostic_id) REFERENCES diagnostics (id)
);

CREATE TABLE compiler_results (
    id UUID NOT NULL, 
    variant_id UUID NOT NULL, 
    compiled_meaning JSONB NOT NULL, 
    compiler_version VARCHAR(50) NOT NULL, 
    result_hash VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(variant_id) REFERENCES guidance_variants (id)
);

CREATE TABLE semantic_comparisons (
    id UUID NOT NULL, 
    compiler_result_id UUID NOT NULL, 
    differences JSONB NOT NULL, 
    is_equivalent BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(compiler_result_id) REFERENCES compiler_results (id)
);

CREATE TABLE simulation_runs (
    id UUID NOT NULL, 
    candidate_id UUID NOT NULL, 
    samples_count INTEGER NOT NULL, 
    failure_frequency FLOAT NOT NULL, 
    wilson_lower FLOAT NOT NULL, 
    wilson_upper FLOAT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES intervention_candidates (id)
);

CREATE TABLE simulation_samples (
    id UUID NOT NULL, 
    simulation_run_id UUID NOT NULL, 
    sample_key VARCHAR(100) NOT NULL, 
    metrics JSONB NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(simulation_run_id) REFERENCES simulation_runs (id)
);

CREATE TABLE simulation_traces (
    id UUID NOT NULL, 
    simulation_run_id UUID NOT NULL, 
    time_series_data JSONB NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(simulation_run_id) REFERENCES simulation_runs (id)
);

CREATE TABLE decision_results (
    id UUID NOT NULL, 
    preflight_run_id UUID NOT NULL, 
    selected_candidate_id UUID, 
    ranking_order JSONB NOT NULL, 
    rank_vectors JSONB NOT NULL, 
    explanation TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(preflight_run_id) REFERENCES preflight_runs (id), 
    FOREIGN KEY(selected_candidate_id) REFERENCES intervention_candidates (id)
);

ALTER TABLE preflight_runs ADD CONSTRAINT fk_preflight_decision_result FOREIGN KEY(decision_result_id) REFERENCES decision_results (id);

CREATE TABLE approval_records (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    approved_by_user_id UUID NOT NULL, 
    approver_role VARCHAR(50) NOT NULL, 
    run_version INTEGER NOT NULL, 
    bundle_hash VARCHAR(64) NOT NULL, 
    approved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    notes TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES preflight_runs (id)
);

CREATE TABLE publication_batches (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR(50) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES preflight_runs (id)
);

CREATE TABLE publication_deliveries (
    id UUID NOT NULL, 
    batch_id UUID NOT NULL, 
    channel VARCHAR(50) NOT NULL, 
    status VARCHAR(50) NOT NULL, 
    error_message TEXT, 
    delivered_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(batch_id) REFERENCES publication_batches (id)
);

CREATE TABLE active_instructions (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    audience_json JSONB NOT NULL, 
    published_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES preflight_runs (id), 
    FOREIGN KEY(venue_id) REFERENCES venues (id)
);

CREATE TABLE audit_events (
    id UUID NOT NULL, 
    session_id UUID NOT NULL, 
    run_id UUID, 
    event_type VARCHAR(100) NOT NULL, 
    payload JSONB NOT NULL, 
    sequence_number INTEGER NOT NULL, 
    previous_event_hash VARCHAR(64) NOT NULL, 
    event_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id), 
    FOREIGN KEY(run_id) REFERENCES preflight_runs (id), 
    CONSTRAINT uq_session_sequence UNIQUE (session_id, sequence_number)
);

CREATE TABLE outbox_events (
    id UUID NOT NULL, 
    event_type VARCHAR(100) NOT NULL, 
    payload JSONB NOT NULL, 
    delivery_status VARCHAR(50) NOT NULL, 
    retry_count INTEGER NOT NULL, 
    available_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    locked_by UUID, 
    locked_at TIMESTAMP WITH TIME ZONE, 
    processed_at TIMESTAMP WITH TIME ZONE, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE idempotency_keys (
    key_hash VARCHAR(64) NOT NULL, 
    session_id UUID, 
    user_id UUID, 
    request_hash VARCHAR(64) NOT NULL, 
    command_type VARCHAR(100) NOT NULL, 
    resource_identifier VARCHAR(100), 
    status VARCHAR(50) NOT NULL, 
    response_status INTEGER, 
    response_body JSONB, 
    lock_acquired_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (key_hash)
);

INSERT INTO alembic_version (version_num) VALUES ('001_baseline') RETURNING alembic_version.version_num;

INFO  [alembic.runtime.migration] Running upgrade 001_baseline -> 002_golden_flow_hardening, Golden flow persistence hardening.
-- Running upgrade 001_baseline -> 002_golden_flow_hardening

ALTER TABLE venue_state_snapshots ADD COLUMN venue_id UUID;

ALTER TABLE venue_state_snapshots ADD COLUMN scenario_key VARCHAR(100);

ALTER TABLE venue_state_snapshots ADD COLUMN reference_data_version VARCHAR(50);

ALTER TABLE venue_state_snapshots ADD COLUMN canonical_input_hash VARCHAR(64);

ALTER TABLE venue_state_snapshots ADD CONSTRAINT fk_snapshot_venue FOREIGN KEY(venue_id) REFERENCES venues (id);

ALTER TABLE operational_intents ADD COLUMN objective VARCHAR(100);

ALTER TABLE operational_intents ADD COLUMN target VARCHAR(100);

ALTER TABLE operational_intents ADD COLUMN affected_audience VARCHAR(150);

ALTER TABLE operational_intents ADD COLUMN constraints JSONB;

ALTER TABLE operational_intents ADD COLUMN excluded_cohorts JSONB;

ALTER TABLE intervention_candidates ADD COLUMN cohort_id VARCHAR(100);

ALTER TABLE intervention_candidates ADD COLUMN preliminary_rank INTEGER;

ALTER TABLE intervention_candidates ADD COLUMN policy_version VARCHAR(50);

ALTER TABLE intervention_candidates ADD COLUMN selected BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE intervention_candidates ADD CONSTRAINT uq_run_candidate_key UNIQUE (run_id, candidate_key);

ALTER TABLE candidate_rejections ADD COLUMN affected_route_id UUID;

ALTER TABLE candidate_rejections ADD COLUMN affected_edge_key VARCHAR(100);

ALTER TABLE candidate_rejections ADD COLUMN affected_asset_key VARCHAR(100);

ALTER TABLE candidate_rejections ADD CONSTRAINT fk_rejection_route FOREIGN KEY(affected_route_id) REFERENCES routes (id);

CREATE TABLE gir_versions (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    instruction_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    gir_data JSONB NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    is_current BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES preflight_runs (id), 
    CONSTRAINT uq_gir_run_version UNIQUE (run_id, version)
);

ALTER TABLE generation_runs ADD COLUMN status VARCHAR(50);

ALTER TABLE generation_runs ADD COLUMN request_count INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE generation_runs ADD COLUMN successful_request_count INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE generation_runs ADD COLUMN safe_error_code VARCHAR(100);

ALTER TABLE generation_runs ADD COLUMN request_id_hash VARCHAR(64);

ALTER TABLE generation_runs ADD COLUMN provenance JSONB;

ALTER TABLE guidance_variants ADD CONSTRAINT uq_generation_variant_version UNIQUE (generation_run_id, language, channel, version);

ALTER TABLE diagnostics ADD COLUMN variant_id UUID;

ALTER TABLE diagnostics ADD COLUMN details JSONB;

ALTER TABLE diagnostics ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE diagnostics ADD CONSTRAINT fk_diagnostic_variant FOREIGN KEY(variant_id) REFERENCES guidance_variants (id);

ALTER TABLE semantic_comparisons ADD COLUMN result_hash VARCHAR(64);

ALTER TABLE simulation_runs ADD COLUMN sample_set_id VARCHAR(160);

ALTER TABLE simulation_runs ADD COLUMN seed INTEGER;

ALTER TABLE simulation_runs ADD COLUMN verdict VARCHAR(20);

ALTER TABLE simulation_runs ADD COLUMN result_hash VARCHAR(64);

ALTER TABLE simulation_runs ADD COLUMN metrics JSONB;

ALTER TABLE approval_records ADD CONSTRAINT uq_approval_run UNIQUE (run_id);

ALTER TABLE publication_batches ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE publication_deliveries RENAME channel TO surface;

ALTER TABLE publication_deliveries ADD COLUMN language VARCHAR(10);

ALTER TABLE publication_deliveries ADD COLUMN variant_id UUID;

ALTER TABLE publication_deliveries ADD CONSTRAINT fk_publication_variant FOREIGN KEY(variant_id) REFERENCES guidance_variants (id);

ALTER TABLE publication_deliveries ADD CONSTRAINT uq_batch_surface_language UNIQUE (batch_id, surface, language);

UPDATE alembic_version SET version_num='002_golden_flow_hardening' WHERE alembic_version.version_num = '001_baseline';

INFO  [alembic.runtime.migration] Running upgrade 002_golden_flow_hardening -> 003_venue_scoped_keys, Scope topology stable keys to their venue.
-- Running upgrade 002_golden_flow_hardening -> 003_venue_scoped_keys

ALTER TABLE venue_nodes DROP CONSTRAINT venue_nodes_stable_key_key;

ALTER TABLE venue_edges DROP CONSTRAINT venue_edges_stable_key_key;

ALTER TABLE venue_assets DROP CONSTRAINT venue_assets_stable_key_key;

ALTER TABLE routes DROP CONSTRAINT routes_stable_key_key;

ALTER TABLE venue_nodes ADD CONSTRAINT uq_venue_node_key UNIQUE (venue_id, stable_key);

ALTER TABLE venue_edges ADD CONSTRAINT uq_venue_edge_key UNIQUE (venue_id, stable_key);

ALTER TABLE venue_assets ADD CONSTRAINT uq_venue_asset_key UNIQUE (venue_id, stable_key);

ALTER TABLE routes ADD CONSTRAINT uq_venue_route_key UNIQUE (venue_id, stable_key);

UPDATE alembic_version SET version_num='003_venue_scoped_keys' WHERE alembic_version.version_num = '002_golden_flow_hardening';

COMMIT;

