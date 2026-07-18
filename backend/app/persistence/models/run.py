from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    TEXT,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from backend.app.persistence.types import JSON_DOCUMENT


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    active_scenario_key: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VenueStateSnapshot(Base):
    __tablename__ = "venue_state_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"), nullable=False)
    scenario_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_data_version: Mapped[str] = mapped_column(String(50), nullable=False)
    canonical_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nodes_state: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    edges_state: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    assets_state: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class OperationalIntent(Base):
    __tablename__ = "operational_intents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    interpreted_objective: Mapped[str | None] = mapped_column(TEXT)
    interpreted_constraints: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_DOCUMENT
    )
    objective: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    affected_audience: Mapped[str] = mapped_column(String(150), nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    excluded_cohorts: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PreflightRun(Base):
    __tablename__ = "preflight_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operational_intents.id"), nullable=False
    )
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "intervention_candidates.id",
            use_alter=True,
            name="fk_preflight_selected_candidate",
        )
    )
    venue_state_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue_state_snapshots.id"), nullable=False
    )
    decision_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "decision_results.id",
            use_alter=True,
            name="fk_preflight_decision_result",
        )
    )
    reference_data_version: Mapped[str] = mapped_column(String(50), nullable=False)
    terminology_version: Mapped[str] = mapped_column(String(50), nullable=False)
    simulation_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    intervention_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    compiler_version: Mapped[str] = mapped_column(String(50), nullable=False)
    fallback_template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    sample_set_version: Mapped[str] = mapped_column(String(50), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_bundle_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __mapper_args__ = {"version_id_col": version_id}


class InterventionCandidate(Base):
    __tablename__ = "intervention_candidates"
    __table_args__ = (
        UniqueConstraint("run_id", "candidate_key", name="uq_run_candidate_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    candidate_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue_nodes.id"), nullable=False
    )
    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.id"), nullable=False)
    cohort_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_viable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preliminary_rank: Mapped[int | None] = mapped_column(Integer)
    policy_version: Mapped[str | None] = mapped_column(String(50))
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CandidateRejection(Base):
    __tablename__ = "candidate_rejections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intervention_candidates.id"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(TEXT, nullable=False)
    affected_route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("routes.id"))
    affected_edge_key: Mapped[str | None] = mapped_column(String(100))
    affected_asset_key: Mapped[str | None] = mapped_column(String(100))


class GIRVersionModel(Base):
    __tablename__ = "gir_versions"
    __table_args__ = (UniqueConstraint("run_id", "version", name="uq_gir_run_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    instruction_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    gir_data: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    preflight_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_request_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(String(100))
    request_id_hash: Mapped[str | None] = mapped_column(String(64))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class GuidanceVariantModel(Base):
    __tablename__ = "guidance_variants"
    __table_args__ = (
        UniqueConstraint(
            "generation_run_id",
            "language",
            "channel",
            "version",
            name="uq_generation_variant_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_runs.id"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    audience_action: Mapped[str] = mapped_column(TEXT, nullable=False)
    route_clause: Mapped[str] = mapped_column(TEXT, nullable=False)
    fallback_clause: Mapped[str] = mapped_column(TEXT, nullable=False)
    protection_clause: Mapped[str] = mapped_column(TEXT, nullable=False)
    validity_clause: Mapped[str] = mapped_column(TEXT, nullable=False)
    optional_explanation: Mapped[str | None] = mapped_column(TEXT)
    rendered_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DiagnosticModel(Base):
    __tablename__ = "diagnostics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_runs.id"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guidance_variants.id")
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(TEXT, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RepairAttemptModel(Base):
    __tablename__ = "repair_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guidance_variants.id"), nullable=False
    )
    diagnostic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnostics.id"), nullable=False
    )
    target_clause: Mapped[str] = mapped_column(String(100), nullable=False)
    original_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    repaired_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_runs.id"), nullable=False
    )
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CompilerResultModel(Base):
    __tablename__ = "compiler_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guidance_variants.id"), nullable=False
    )
    compiled_meaning: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )
    compiler_version: Mapped[str] = mapped_column(String(50), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SemanticComparisonModel(Base):
    __tablename__ = "semantic_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    compiler_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compiler_results.id"), nullable=False
    )
    differences: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )
    is_equivalent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SimulationRunModel(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intervention_candidates.id"), nullable=False
    )
    sample_set_id: Mapped[str] = mapped_column(String(160), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    samples_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_frequency: Mapped[float] = mapped_column(Float, nullable=False)
    wilson_lower: Mapped[float] = mapped_column(Float, nullable=False)
    wilson_upper: Mapped[float] = mapped_column(Float, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class SimulationSampleModel(Base):
    __tablename__ = "simulation_samples"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False
    )
    sample_key: Mapped[str] = mapped_column(String(100), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class SimulationTraceModel(Base):
    __tablename__ = "simulation_traces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False
    )
    time_series_data: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )


class DecisionResultModel(Base):
    __tablename__ = "decision_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    preflight_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("intervention_candidates.id")
    )
    ranking_order: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    rank_vectors: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    explanation: Mapped[str] = mapped_column(TEXT, nullable=False)


class ApprovalRecordModel(Base):
    __tablename__ = "approval_records"
    __table_args__ = (UniqueConstraint("run_id", name="uq_approval_run"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    approved_by_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    approver_role: Mapped[str] = mapped_column(String(50), nullable=False)
    run_version: Mapped[int] = mapped_column(Integer, nullable=False)
    bundle_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(TEXT)


class PublicationBatchModel(Base):
    __tablename__ = "publication_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False)


class PublicationDeliveryModel(Base):
    __tablename__ = "publication_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "surface", "language", name="uq_batch_surface_language"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publication_batches.id"), nullable=False
    )
    surface: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("guidance_variants.id")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(TEXT)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActiveInstructionModel(Base):
    __tablename__ = "active_instructions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preflight_runs.id"), nullable=False
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"), nullable=False)
    audience_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column()
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    command_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_identifier: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    lock_acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column()
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(TEXT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
