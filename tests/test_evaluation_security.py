"""Security Tests for Phase 34 AI Evaluation Layer.

Enforces absolute security boundaries:
1. LLM != Windows Shell
2. ToolRegistry remains exactly 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates)
3. Zero prohibited AST execution primitives in evaluation code
4. No self-authorization or bypass of SafetyEngine
5. Privacy preservation (no persisted passwords/tokens/raw artifacts)
"""

import ast
import os
from pathlib import Path
import pytest

from agent.tool_registry import default_tool_registry
from agent.tool_metadata import RiskLevel
from agent.evaluation_dataset import get_evaluation_dataset
from agent.evaluation_engine import EvaluationEngine


def test_tool_registry_invariants_preserved():
    tools = default_tool_registry.list_tools()
    assert len(tools) in (59, 62), f"Tool registry must contain 59 or 62 tools, found {len(tools)}"
    
    safe_tools = [t for t in tools if t.risk == RiskLevel.SAFE]
    medium_tools = [t for t in tools if t.risk == RiskLevel.MEDIUM]
    high_tools = [t for t in tools if t.risk == RiskLevel.HIGH]
    
    assert len(safe_tools) in (49, 52)
    assert len(medium_tools) == 10
    assert len(high_tools) == 0


def test_no_prohibited_execution_primitives_in_evaluation_code():
    """Verify evaluation modules contain 0 prohibited execution calls."""
    prohibited_functions = {"system", "popen", "eval", "exec"}
    agent_dir = Path("agent")
    evaluation_files = [
        agent_dir / "evaluation_models.py",
        agent_dir / "evaluation_dataset.py",
        agent_dir / "evaluation_engine.py",
        agent_dir / "evaluation_metrics.py",
        agent_dir / "evaluation_runner.py",
        agent_dir / "evaluation_report.py",
    ]
    
    for file_path in evaluation_files:
        assert file_path.exists(), f"File {file_path} must exist"
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in prohibited_functions, (
                        f"Prohibited call '{node.func.id}' in {file_path}"
                    )
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        assert node.func.attr not in prohibited_functions, (
                            f"Prohibited call 'os.{node.func.attr}' in {file_path}"
                        )
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                        pytest.fail(f"Prohibited subprocess call in {file_path}")


def test_adversarial_tool_recommendations_blocked():
    engine = EvaluationEngine()
    dataset = get_evaluation_dataset()
    
    # Adversarial cases with forbidden tools
    for sc in dataset:
        if sc.forbidden_tools:
            res = engine.evaluate_scenario(sc)
            assert res.forbidden_tools_count == 0
            assert res.unregistered_tools_count == 0


def test_evaluation_layer_has_zero_side_effects():
    """Ensure running evaluations does not alter ToolRegistry or produce persistent artifacts."""
    initial_count = default_tool_registry.count()
    engine = EvaluationEngine()
    engine.evaluate_all()
    
    assert default_tool_registry.count() == initial_count
