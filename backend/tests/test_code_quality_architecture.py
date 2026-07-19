from __future__ import annotations

import ast
import importlib
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
    """Enforce GoldenFlowService is a thin compatibility facade."""
    facade = SERVICE_ROOT / "golden_flow_service.py"
    lines = len(facade.read_text(encoding="utf-8").splitlines())
    assert lines <= 80, f"GoldenFlowService should be ≤80 lines, got {lines}"

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
    """Ensure workflows are flat and avoid inheritance chains."""
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
        lines = len(module.read_text(encoding="utf-8").splitlines())
        assert lines <= 400, f"{module.name} exceeds 400 lines: {lines}"
        assert "backend.app.api" not in module.read_text(
            encoding="utf-8"
        ), f"{module.name} should not import backend.app.api"


def test_read_queries_does_not_import_api_modules() -> None:
    """Enforce read_queries.py is pure database query layer."""
    queries_file = WORKFLOW_ROOT / "read_queries.py"
    content = queries_file.read_text(encoding="utf-8")
    forbidden_modules = [
        "backend.app.api",
        "sqlalchemy.orm.schema",
        "pydantic",
    ]
    for module in forbidden_modules:
        assert module not in content, f"read_queries.py should not import {module}"


def test_read_serializers_does_not_import_sqlalchemy() -> None:
    """Enforce read_serializers.py is pure transformation layer."""
    serializers_file = WORKFLOW_ROOT / "read_serializers.py"
    content = serializers_file.read_text(encoding="utf-8")
    assert (
        "sqlalchemy" not in content
    ), "read_serializers.py should not import sqlalchemy"
    assert (
        "Session" not in content
    ), "read_serializers.py should not reference SQLAlchemy Session"


def test_read_model_remains_orchestration_only() -> None:
    """Enforce read_model.py delegates to queries and serializers."""
    model_file = WORKFLOW_ROOT / "read_model.py"
    content = model_file.read_text(encoding="utf-8")
    lines = len(content.splitlines())
    assert lines <= 100, f"read_model.py should be ≤100 lines, got {lines}"

    tree = ast.parse(content)
    class_defs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "ReadModel"
    ]
    assert len(class_defs) == 1, "read_model.py should have exactly one ReadModel class"

    read_model_class = class_defs[0]
    methods = [
        node.name
        for node in read_model_class.body
        if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef)
    ]
    for method in methods:
        if method.startswith("_"):
            continue
        assert any(
            func_name in content for func_name in ["ReadQueries", "ReadSerializers"]
        ), f"{method} should delegate to ReadQueries or ReadSerializers"


def _get_all_imports(tree: ast.AST) -> set[str]:
    """Extract all module imports from AST."""
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_no_circular_imports_in_golden_flow() -> None:
    """Ensure no circular imports within golden_flow modules."""
    modules_to_check = [
        "backend.app.services.golden_flow.read_model",
        "backend.app.services.golden_flow.read_queries",
        "backend.app.services.golden_flow.read_serializers",
        "backend.app.services.golden_flow.run_workflow",
    ]

    import_graph = {}
    for module_name in modules_to_check:
        try:
            module = importlib.import_module(module_name)
            module_path = Path(module.__file__) if module.__file__ else None
            if module_path:
                content = module_path.read_text(encoding="utf-8")
                tree = ast.parse(content)
                imports = _get_all_imports(tree)
                import_graph[module_name] = imports
        except (ImportError, AttributeError):
            pass

    for module_name, imports in import_graph.items():
        for imported in imports:
            if imported.startswith("backend.app.services.golden_flow"):
                reverse_imports = import_graph.get(imported, set())
                assert (
                    module_name not in reverse_imports
                ), f"Circular import detected: {module_name} <-> {imported}"


def test_public_functions_have_explicit_return_annotations() -> None:
    """Ensure all public methods have explicit return type hints."""
    public_modules = [
        WORKFLOW_ROOT / "read_model.py",
        WORKFLOW_ROOT / "read_queries.py",
        WORKFLOW_ROOT / "read_serializers.py",
    ]

    for module_file in public_modules:
        content = module_file.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    assert (
                        node.returns is not None
                    ), f"{module_file.name}: {node.name} missing return annotation"
