"""Type definitions for read-model API responses.

Structured types for serialized run data, replacing generic dict[str, Any].
Preserves all existing JSON keys, optional fields, and API contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID


class RejectionView(TypedDict):
    """Serialized candidate rejection."""

    reason_code: str
    message: str
    affected_route_id: str | UUID | None
    affected_edge_key: str | None
    affected_asset_key: str | None


class CandidateView(TypedDict):
    """Serialized intervention candidate with rejections."""

    id: UUID
    candidate_key: str
    title: str
    cohort_id: str
    destination_id: UUID | str
    route_id: UUID | str
    is_viable: bool
    preliminary_rank: int | None
    selected: bool
    rejections: list[RejectionView]


class GuidanceVariantView(TypedDict):
    """Serialized guidance variant."""

    id: UUID
    language: str
    channel: str
    version: int
    audience_action: str
    route_clause: str
    fallback_clause: str
    protection_clause: str
    validity_clause: str
    optional_explanation: str | None
    rendered_text: str
    content_hash: str


class DiagnosticView(TypedDict):
    """Serialized generation diagnostic."""

    id: UUID
    code: str
    stage: str
    severity: str
    message: str
    details: str | dict[str, Any] | None
    blocking: bool
    resolved_at: str | datetime | None


class ApprovalView(TypedDict):
    """Serialized approval record."""

    approved_by_user_id: str
    approver_role: str
    run_version: int
    bundle_hash: str
    approval_note: str | None
    approved_at: str | datetime


class PublicationBatchView(TypedDict):
    """Serialized publication batch."""

    id: UUID
    status: str
    started_at: str | datetime
    completed_at: str | datetime | None


class PublicationDeliveryView(TypedDict):
    """Serialized publication delivery."""

    surface: str
    language: str
    status: str
    variant_id: UUID | None
    error_message: str | None
    delivered_at: str | datetime | None


class SnapshotView(TypedDict):
    """Serialized venue state snapshot."""

    id: UUID
    session_id: str | UUID
    venue_id: str | UUID
    scenario_key: str
    reference_data_version: str
    canonical_input_hash: str
    timestamp: str | datetime
    nodes_state: dict[str, Any] | None
    edges_state: dict[str, Any] | None
    assets_state: dict[str, Any] | None


class AuditEventView(TypedDict):
    """Serialized audit event."""

    id: UUID
    sequence_number: int
    event_type: str
    payload: dict[str, Any]
    created_at: str | datetime
    previous_event_hash: str | None
    event_hash: str


class GoldenFlowDetailsResponse(TypedDict):
    """Complete run details response."""

    run_id: UUID
    session_id: str | UUID
    scenario_key: str
    lifecycle_state: str
    run_version: int
    selected_candidate_id: UUID | None
    snapshot_hash: str
    gir: dict[str, Any] | None
    candidates: list[CandidateView]
    generation_provenance: dict[str, Any] | None
    variants: list[GuidanceVariantView]
    diagnostics: list[DiagnosticView]
    simulation: dict[str, Any] | None
    approval: ApprovalView | None
    publication_batch: PublicationBatchView | None
    publication_deliveries: list[PublicationDeliveryView]
    expected_bundle_hash: str | None
    decision_bundle_hash: str | None
