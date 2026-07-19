from __future__ import annotations

from pathlib import Path

from backend.app.services.golden_flow.approval_workflow import ApprovalWorkflow
from backend.app.services.golden_flow.guidance_workflow import GuidanceWorkflow
from backend.app.services.golden_flow.publication_workflow import PublicationWorkflow
from backend.app.services.golden_flow.read_model import ReadModel
from backend.app.services.golden_flow.repair_workflow import RepairWorkflow
from backend.app.services.golden_flow.run_workflow import RunWorkflow
from backend.app.services.golden_flow.simulation_workflow import SimulationWorkflow
from backend.app.services.golden_flow_service import GoldenFlowService

SERVICE_ROOT = Path(__file__).parents[1] / "app" / "services"
WORKFLOW_ROOT = SERVICE_ROOT / "golden_flow"


def test_golden_flow_facade_remains_small_and_stable() -> None:
    facade = SERVICE_ROOT / "golden_flow_service.py"
    assert len(facade.read_text(encoding="utf-8").splitlines()) <= 60

    public_operations = {
        "create_run",
        "select_candidate",
        "generate_guidance",
        "repair",
        "simulate",
        "expected_bundle_hash",
        "approve",
        "publish",
        "details",
        "snapshot_details",
        "audit_timeline",
    }
    assert all(hasattr(GoldenFlowService, name) for name in public_operations)


def test_workflows_are_focused_without_inheritance_chain() -> None:
    workflows = (
        RunWorkflow,
        GuidanceWorkflow,
        RepairWorkflow,
        SimulationWorkflow,
        ApprovalWorkflow,
        PublicationWorkflow,
        ReadModel,
    )
    assert all(workflow.__bases__ == (object,) for workflow in workflows)

    for module in WORKFLOW_ROOT.glob("*.py"):
        assert len(module.read_text(encoding="utf-8").splitlines()) <= 400
        assert "backend.app.api" not in module.read_text(encoding="utf-8")
