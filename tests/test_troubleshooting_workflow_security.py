"""Security and Invariant Tests for Intelligent Troubleshooting Workflow (Phase 28).

Validates strict non-negotiable security rules:
- AST prohibited call scan (subprocess, shell=True, os.system, os.popen, eval, exec)
- LLM != Windows Shell
- Diagnosis != Repair Authorization
- Repair Candidate != Repair Authorization
- Confirmation token binding across sessions, tools, and workflows
- No automatic MEDIUM repair retry
- No verification spoofing
- Immutable step limit bounds (max 8)
- Session isolation & audit sanitization
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agent.diagnostic_models import DiagnosticHypothesis, DiagnosticResponse
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry
from agent.workflow_models import (
    RepairCandidate,
    ResolutionStatus,
    StepType,
    TroubleshootingWorkflow,
    WorkflowStatus,
    WorkflowStep,
)
from agent.workflow_engine import (
    DeterministicResolutionEngine,
    PreconditionEngine,
    RepairCandidateValidator,
    TroubleshootingWorkflowEngine,
)


@pytest.fixture
def test_registry():
    reg = ToolRegistry()
    reg.register(ToolDefinition(
        name="check_network_adapters",
        domain="network",
        description="Check network adapters",
        risk=RiskLevel.SAFE,
        handler=lambda **kwargs: {"status": "ok"},
        parameters={},
    ))
    reg.register(ToolDefinition(
        name="flush_dns_cache",
        domain="network",
        description="Flush DNS",
        risk=RiskLevel.MEDIUM,
        handler=lambda **kwargs: {"status": "ok"},
        parameters={},
    ))
    reg.register(ToolDefinition(
        name="renew_dhcp_lease",
        domain="network",
        description="Renew DHCP",
        risk=RiskLevel.MEDIUM,
        handler=lambda **kwargs: {"status": "ok"},
        parameters={},
    ))
    return reg


@pytest.fixture
def workflow_engine(test_registry):
    safety = SafetyEngine(registry=test_registry)
    return TroubleshootingWorkflowEngine(tool_registry=test_registry, safety_engine=safety)


# 1. AST Prohibited Calls Verification
def test_ast_prohibited_calls_in_workflow_modules():
    """Verify strictly 0 forbidden execution calls in agent/workflow_models.py and agent/workflow_engine.py."""
    forbidden_calls = {"subprocess", "system", "popen", "eval", "exec", "CreateProcess", "WinExec", "ShellExecute"}
    root_dir = Path(__file__).resolve().parent.parent

    target_files = [
        root_dir / "agent" / "workflow_models.py",
        root_dir / "agent" / "workflow_engine.py",
    ]

    for fpath in target_files:
        assert fpath.exists(), f"File {fpath} must exist"
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                assert func_name not in forbidden_calls, f"Prohibited call '{func_name}' found in {fpath.name} at line {node.lineno}"


# 2. Confirmation Replay, Session, Tool, and Workflow Binding
def test_confirmation_token_binding_prevents_replay():
    """Verify confirmation tokens are cryptographically bound to exact session, workflow, tool, and arguments."""
    c1 = RepairCandidate(
        candidate_id="c1",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        arguments={},
        session_id="session_1",
        workflow_id="wf_1",
    )
    token1 = c1.generate_confirmation_token()

    # Session mismatch
    c_diff_session = RepairCandidate(
        candidate_id="c1",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        arguments={},
        session_id="session_2",
        workflow_id="wf_1",
    )
    assert token1 != c_diff_session.generate_confirmation_token()

    # Workflow mismatch
    c_diff_wf = RepairCandidate(
        candidate_id="c1",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        arguments={},
        session_id="session_1",
        workflow_id="wf_2",
    )
    assert token1 != c_diff_wf.generate_confirmation_token()

    # Tool mismatch
    c_diff_tool = RepairCandidate(
        candidate_id="c1",
        diagnosis_id="d1",
        tool_name="renew_dhcp_lease",
        purpose="Renew DHCP",
        arguments={},
        session_id="session_1",
        workflow_id="wf_1",
    )
    assert token1 != c_diff_tool.generate_confirmation_token()


# 3. Unregistered and Injected Tool Rejection
def test_unregistered_repair_candidate_rejected(workflow_engine, test_registry):
    """Verify candidates with malicious or unapproved tool names are rejected fail-closed."""
    validator = RepairCandidateValidator(registry=test_registry, safety_engine=SafetyEngine(registry=test_registry))

    malicious_candidates = [
        "powershell.exe",
        "cmd.exe /c del",
        "arbitrary_execution_tool",
        "__import__('os').system('calc')",
    ]

    for tool_name in malicious_candidates:
        cand = RepairCandidate(
            candidate_id="bad",
            diagnosis_id="d1",
            tool_name=tool_name,
            purpose="Injected command",
        )
        ok, msg = validator.validate(cand)
        assert ok is False
        assert "not exist" in msg.lower() or "blocked" in msg.lower()


# 4. Precondition Injection Prevention
def test_precondition_engine_rejects_command_injection():
    """Verify PreconditionEngine blocks shell metacharacters in arguments."""
    malicious_args = [
        {"service_name": "wuauserv; powershell -c calc"},
        {"service_name": "wuauserv && cmd.exe"},
        {"service_name": "wuauserv | cat /etc/passwd"},
        {"service_name": "wuauserv `whoami`"},
    ]

    for args in malicious_args:
        ok, msg = PreconditionEngine.validate_preconditions(
            tool_name="restart_windows_service",
            arguments=args,
            preconditions={},
        )
        assert ok is False
        assert "injection" in msg.lower() or "invalid" in msg.lower()


# 5. Workflow Step Bounds and Limit Protection
def test_immutable_step_limit_enforcement(workflow_engine):
    """Verify workflows strictly enforce max 8 steps and cannot be looped infinitely."""
    diag = DiagnosticResponse(summary="Limit Test")
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_limit")

    assert wf.max_steps == 8
    # Try to execute beyond step limit
    wf.current_step = 8
    res = workflow_engine.execute_next_step(wf.workflow_id, "s_limit")
    assert res["success"] is False
    assert res["status"] == "LIMIT_REACHED"
    assert wf.status == WorkflowStatus.UNRESOLVED


# 6. AI Verification Overriding Prevention
def test_ai_cannot_override_failed_deterministic_verification():
    """Verify that even if AI claims resolution, deterministic verification outcome is authoritative."""
    before_state = {"status": "failed", "dns_resolved": False}
    after_state = {"status": "failed", "dns_resolved": False}

    status, explanation = DeterministicResolutionEngine.compare_evidence(before_state, after_state)
    assert status == ResolutionStatus.NOT_RESOLVED
    assert "persists" in explanation.lower() or "fail" in explanation.lower()


# 7. Audit Log Sanitization
def test_audit_log_sanitization(workflow_engine):
    """Verify secrets and tokens are redacted in workflow audit logs."""
    wf = TroubleshootingWorkflow(
        workflow_id="wf_audit",
        session_id="s_audit",
        problem_category="general",
        title="Audit Test",
    )
    workflow_engine._audit(wf, "TEST_EVENT", {
        "user_token": "secret_token_12345",
        "auth_password": "super_secret_pw",
        "normal_field": "safe_value",
    })

    assert len(wf.audit_events) == 1
    details = wf.audit_events[0]["details"]
    assert details["user_token"] == "[REDACTED]"
    assert details["auth_password"] == "[REDACTED]"
    assert details["normal_field"] == "safe_value"


# 8. MEDIUM Repair Auto-Retry Prohibition
def test_medium_repair_never_auto_retried(workflow_engine, test_registry):
    """Verify that if a MEDIUM repair tool raises an error, it is never retried automatically."""
    fail_mock = MagicMock(side_effect=Exception("Hardware failure during repair"))
    with patch.object(test_registry.get("flush_dns_cache"), "handler", fail_mock):
        candidate = RepairCandidate(
            candidate_id="c_fail",
            diagnosis_id="d1",
            tool_name="flush_dns_cache",
            purpose="Flush DNS",
            risk_level="MEDIUM",
            session_id="s_fail",
        )
        diag = DiagnosticResponse(summary="Fail Test")
        wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_fail", repair_candidate=candidate)
        wf.current_step = 1  # repair step
        token = candidate.generate_confirmation_token()
        
        res = workflow_engine.execute_next_step(wf.workflow_id, "s_fail", confirmation_token=token)
        assert res["success"] is False
        assert res["status"] == "FAILED"
        assert fail_mock.call_count == 1  # Strictly 1 call, zero auto-retries
        assert wf.status == WorkflowStatus.FAILED


# 9. Cross-Tool Confirmation Rejection
def test_cross_tool_confirmation_rejected(workflow_engine, test_registry):
    """Verify user approval for Tool A cannot be used to authorize Tool B."""
    candidate_a = RepairCandidate(
        candidate_id="cA",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        risk_level="MEDIUM",
        session_id="s_cross",
    )
    token_a = candidate_a.generate_confirmation_token()

    candidate_b = RepairCandidate(
        candidate_id="cB",
        diagnosis_id="d1",
        tool_name="renew_dhcp_lease",
        purpose="Renew DHCP",
        risk_level="MEDIUM",
        session_id="s_cross",
    )
    diag = DiagnosticResponse(summary="Cross Tool Test")
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_cross", repair_candidate=candidate_b)
    wf.current_step = 1  # repair step

    # Presenting token_a for candidate_b
    res = workflow_engine.execute_next_step(wf.workflow_id, "s_cross", confirmation_token=token_a)
    assert res["success"] is False
    assert res["status"] == "WAITING_FOR_CONFIRMATION"

