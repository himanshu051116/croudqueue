from __future__ import annotations

from backend.app.services.golden_flow.approval_workflow import ApprovalWorkflow
from backend.app.services.golden_flow.common import (
    OwnershipError,
    RunNotFoundError,
    TransitionError,
    ValidationError,
)
from backend.app.services.golden_flow.guidance_workflow import GuidanceWorkflow
from backend.app.services.golden_flow.publication_workflow import PublicationWorkflow
from backend.app.services.golden_flow.read_model import ReadModel
from backend.app.services.golden_flow.repair_workflow import RepairWorkflow
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.golden_flow.simulation_workflow import SimulationWorkflow


class GoldenFlowService:
    """Stable API facade over focused Golden Flow workflows."""

    create_run = RunWorkflow.create_run
    select_candidate = RunWorkflow.select_candidate
    generate_guidance = GuidanceWorkflow.generate_guidance
    repair = RepairWorkflow.repair
    simulate = SimulationWorkflow.simulate
    expected_bundle_hash = ApprovalWorkflow.expected_bundle_hash
    approve = ApprovalWorkflow.approve
    publish = PublicationWorkflow.publish
    details = ReadModel.details
    snapshot_details = ReadModel.snapshot_details
    audit_timeline = ReadModel.audit_timeline


__all__ = [
    "GoldenFlowService",
    "OwnershipError",
    "RunNotFoundError",
    "TransitionError",
    "ValidationError",
]
