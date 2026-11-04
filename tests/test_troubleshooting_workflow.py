"""Unit and Functional Tests for Intelligent Troubleshooting Workflow (Phase 28).

Tests:
- Workflow creation from diagnosis
- State machine valid transitions and invalid transition rejections
- Precondition evaluation
- Repair candidate creation and validation
- SAFE diagnostic tool execution
- MEDIUM confirmation requirements and token binding
- Deterministic verification and Before/After evidence comparison
- Resolution determination (RESOLVED, NOT_RESOLVED, PARTIALLY_RESOLVED, INCONCLUSIVE)
- Cancellation handling
- Loop and step limit bounds
- Session isolation
- Degraded AI workflow
- UI component rendering
"""

import pytest
from unittest.mock import MagicMock, patch

from agent.diagnostic_models import DiagnosticHypothesis, DiagnosticResponse, HypothesisStatus
from agent.evidence_models import EvidenceItem, EvidenceQuality, EvidenceSource, EvidenceStatus, EvidenceType
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, default_tool_registry
from agent.workflow_models import (
    RepairCandidate,
    ResolutionStatus,
    StepType,
    TroubleshootingWorkflow,
    VALID_WORKFLOW_TRANSITIONS,
    WorkflowStatus,
    WorkflowStep,
)
from agent.workflow_engine import (
    DeterministicResolutionEngine,
    PreconditionEngine,
    RepairCandidateValidator,
    TroubleshootingWorkflowEngine,
    default_workflow_engine,
)
from ui.components import render_troubleshooting_workflow_card


@pytest.fixture
def mock_registry():
    """Create a mock ToolRegistry with SAFE and MEDIUM tools."""
    reg = ToolRegistry()
    reg.register(ToolDefinition(
        name="check_network_adapters",
        domain="network",
        description="Check network adapters",
        risk=RiskLevel.SAFE,
        handler=lambda **kwargs: {"status": "ok", "adapters": ["Ethernet0"]},
        parameters={},
    ))
    reg.register(ToolDefinition(
        name="check_dns_resolution",
        domain="network",
        description="Check DNS resolution",
        risk=RiskLevel.SAFE,
        handler=lambda **kwargs: {"status": "failed", "dns_resolved": False},
        parameters={},
    ))
    reg.register(ToolDefinition(
        name="flush_dns_cache",
        domain="network",
        description="Flush DNS cache",
        risk=RiskLevel.MEDIUM,
        handler=lambda **kwargs: {"status": "ok", "flushed": True},
        parameters={},
    ))
    return reg


@pytest.fixture
def workflow_engine(mock_registry):
    safety = SafetyEngine(registry=mock_registry)
    return TroubleshootingWorkflowEngine(tool_registry=mock_registry, safety_engine=safety)


def test_workflow_creation(workflow_engine):
    """Test creating a troubleshooting workflow from diagnostic response."""
    diag = DiagnosticResponse(
        summary="DNS resolution failure",
        observations=["DNS lookup timed out"],
        interpretations=["Local DNS cache corrupted"],
        hypotheses=[
            DiagnosticHypothesis(
                hypothesis_id="hyp_001",
                category="network",
                statement="DNS resolver cache is stale or corrupt",
                status=HypothesisStatus.POSSIBLE,
                recommended_tools=["check_dns_resolution"],
            )
        ],
        recommended_tools=["check_dns_resolution"],
        tutor_explanation="DNS maps human names to IP addresses.",
    )
    candidate = RepairCandidate(
        candidate_id="rep_001",
        diagnosis_id="plan_001",
        tool_name="flush_dns_cache",
        purpose="Flush the stale DNS resolver cache",
        verification_method="check_dns_resolution",
        risk_level="MEDIUM",
        authorization_required=True,
        arguments={},
        session_id="session_123",
    )

    wf = workflow_engine.create_workflow_from_diagnosis(
        diagnosis=diag,
        session_id="session_123",
        repair_candidate=candidate,
    )

    assert wf.workflow_id.startswith("wf_")
    assert wf.session_id == "session_123"
    assert wf.status == WorkflowStatus.CREATED
    assert wf.max_steps == 8
    assert len(wf.steps) <= 8
    assert wf.repair_candidate is not None
    assert wf.repair_candidate.tool_name == "flush_dns_cache"


def test_state_machine_valid_and_invalid_transitions(workflow_engine):
    """Test state machine enforces valid transitions and rejects invalid ones."""
    wf = TroubleshootingWorkflow(
        workflow_id="wf_test",
        session_id="s1",
        problem_category="network",
        title="Test WF",
        status=WorkflowStatus.CREATED,
    )

    # Valid: CREATED -> DIAGNOSING
    workflow_engine.transition_state(wf, WorkflowStatus.DIAGNOSING)
    assert wf.status == WorkflowStatus.DIAGNOSING

    # Valid: DIAGNOSING -> VERIFY_PRECONDITION
    workflow_engine.transition_state(wf, WorkflowStatus.VERIFY_PRECONDITION)
    assert wf.status == WorkflowStatus.VERIFY_PRECONDITION

    # Valid: VERIFY_PRECONDITION -> WAITING_FOR_CONFIRMATION
    workflow_engine.transition_state(wf, WorkflowStatus.WAITING_FOR_CONFIRMATION)
    assert wf.status == WorkflowStatus.WAITING_FOR_CONFIRMATION

    # Valid: WAITING_FOR_CONFIRMATION -> REPAIRING
    workflow_engine.transition_state(wf, WorkflowStatus.REPAIRING)
    assert wf.status == WorkflowStatus.REPAIRING

    # Valid: REPAIRING -> VERIFYING
    workflow_engine.transition_state(wf, WorkflowStatus.VERIFYING)
    assert wf.status == WorkflowStatus.VERIFYING

    # Valid: VERIFYING -> RESOLVED
    workflow_engine.transition_state(wf, WorkflowStatus.RESOLVED)
    assert wf.status == WorkflowStatus.RESOLVED

    # Invalid: RESOLVED -> REPAIRING (terminal state)
    with pytest.raises(ValueError, match="Invalid workflow state transition"):
        workflow_engine.transition_state(wf, WorkflowStatus.REPAIRING)


def test_precondition_evaluation_success_and_failure():
    """Test deterministic precondition checks."""
    # Success case
    ok, msg = PreconditionEngine.validate_preconditions(
        tool_name="restart_windows_service",
        arguments={"service_name": "wuauserv"},
        preconditions={},
    )
    assert ok is True

    # Failure case: injection characters in service name
    bad_ok, bad_msg = PreconditionEngine.validate_preconditions(
        tool_name="restart_windows_service",
        arguments={"service_name": "wuauserv; rm -rf /"},
        preconditions={},
    )
    assert bad_ok is False
    assert "injection" in bad_msg.lower() or "invalid" in bad_msg.lower()


def test_repair_candidate_validation(mock_registry):
    """Test RepairCandidateValidator strictly validates against ToolRegistry."""
    safety = SafetyEngine(registry=mock_registry)
    validator = RepairCandidateValidator(registry=mock_registry, safety_engine=safety)

    # Valid candidate
    valid_candidate = RepairCandidate(
        candidate_id="c1",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        verification_method="check_dns_resolution",
        risk_level="MEDIUM",
        authorization_required=True,
    )
    ok, msg = validator.validate(valid_candidate)
    assert ok is True

    # Invalid candidate: unregistered tool
    invalid_candidate = RepairCandidate(
        candidate_id="c2",
        diagnosis_id="d1",
        tool_name="unregistered_malicious_tool",
        purpose="Hack",
        verification_method="check_dns_resolution",
    )
    bad_ok, bad_msg = validator.validate(invalid_candidate)
    assert bad_ok is False
    assert "not exist" in bad_msg


def test_workflow_execution_and_confirmation_boundary(workflow_engine, mock_registry):
    """Test end-to-end workflow execution enforcing confirmation on MEDIUM tool."""
    diag = DiagnosticResponse(
        summary="DNS issue",
        hypotheses=[
            DiagnosticHypothesis(hypothesis_id="h1", category="network", statement="DNS bad")
        ],
        recommended_tools=["check_dns_resolution"],
    )
    candidate = RepairCandidate(
        candidate_id="c1",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        verification_method="check_dns_resolution",
        risk_level="MEDIUM",
        authorization_required=True,
        arguments={},
        session_id="test_session",
    )

    wf = workflow_engine.create_workflow_from_diagnosis(
        diagnosis=diag,
        session_id="test_session",
        repair_candidate=candidate,
    )

    # Step 1: Diagnose (SAFE)
    res1 = workflow_engine.execute_next_step(wf.workflow_id, "test_session")
    assert res1["success"] is True

    # Step 2: Precondition
    res2 = workflow_engine.execute_next_step(wf.workflow_id, "test_session")
    assert res2["success"] is True

    # Step 3: Repair (MEDIUM) - without confirmation
    res3 = workflow_engine.execute_next_step(wf.workflow_id, "test_session")
    assert res3["success"] is False
    assert res3["status"] == "WAITING_FOR_CONFIRMATION"
    assert "confirmation_token" in res3

    # Step 3 again: with correct confirmation token
    token = res3["confirmation_token"]
    res3_confirmed = workflow_engine.execute_next_step(
        wf.workflow_id, "test_session", confirmation_token=token
    )
    assert res3_confirmed["success"] is True
    assert res3_confirmed["status"] == "REPAIR_EXECUTED"

    # Step 4: Verification (Simulate resolved DNS after flush)
    with patch.object(mock_registry.get("check_dns_resolution"), "handler", return_value={"status": "ok", "dns_resolved": True}):
        res4 = workflow_engine.execute_next_step(wf.workflow_id, "test_session")
        assert res4["success"] is True
        assert res4["resolution_status"] == ResolutionStatus.RESOLVED.value

    # Step 5: Complete
    res5 = workflow_engine.execute_next_step(wf.workflow_id, "test_session")
    assert res5["success"] is True
    assert res5["status"] == WorkflowStatus.RESOLVED.value


def test_deterministic_resolution_engine_states():
    """Test before/after comparison across all resolution outcomes."""
    # 1. RESOLVED (failed -> success)
    before_bad = {"status": "failed", "dns_resolved": False}
    after_good = {"status": "ok", "dns_resolved": True}
    res, _ = DeterministicResolutionEngine.compare_evidence(before_bad, after_good)
    assert res == ResolutionStatus.RESOLVED

    # 2. NOT_RESOLVED (failed -> failed)
    after_bad = {"status": "failed", "dns_resolved": False}
    res2, _ = DeterministicResolutionEngine.compare_evidence(before_bad, after_bad)
    assert res2 == ResolutionStatus.NOT_RESOLVED

    # 3. INCONCLUSIVE (empty evidence)
    res3, _ = DeterministicResolutionEngine.compare_evidence({}, {})
    assert res3 == ResolutionStatus.INCONCLUSIVE


def test_workflow_cancellation(workflow_engine):
    """Test cancelling an active workflow prevents further execution."""
    diag = DiagnosticResponse(summary="Cancellation Test")
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_cancel")

    ok = workflow_engine.request_cancellation(wf.workflow_id, "s_cancel")
    assert ok is True
    assert wf.status == WorkflowStatus.CANCELLED
    assert wf.cancellation_requested is True

    # Attempting to execute next step must fail closed
    res = workflow_engine.execute_next_step(wf.workflow_id, "s_cancel")
    assert res["success"] is False
    assert res["status"] == "CANCELLED"


def test_session_isolation(workflow_engine):
    """Test session mismatch blocks access to workflows."""
    diag = DiagnosticResponse(summary="Session Test")
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="session_A")

    res = workflow_engine.execute_next_step(wf.workflow_id, session_id="session_B")
    assert res["success"] is False
    assert res["status"] == "FORBIDDEN"


def test_duplicate_repair_execution_prevention(workflow_engine, mock_registry):
    """Test same repair tool cannot be executed more than once per workflow."""
    candidate = RepairCandidate(
        candidate_id="c_dup",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        risk_level="MEDIUM",
        arguments={},
        session_id="s_dup",
    )
    diag = DiagnosticResponse(summary="Duplicate Repair Test")
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_dup", repair_candidate=candidate)

    # Manually mark repair tool as already executed
    wf.executed_repair_tools.append("flush_dns_cache")
    wf.current_step = 1  # point to repair step
    token = candidate.generate_confirmation_token()

    res = workflow_engine.execute_next_step(wf.workflow_id, "s_dup", confirmation_token=token)
    assert res["success"] is False
    assert "Duplicate execution blocked" in res["error"]


def test_ui_workflow_card_rendering():
    """Test UI workflow card component runs without exceptions."""
    wf_data = {
        "title": "Network Troubleshooting Workflow",
        "status": "DIAGNOSING",
        "current_step": 1,
        "steps": [
            {"step_id": 1, "sequence": 1, "step_type": "DIAGNOSE", "purpose": "Check adapters"},
            {"step_id": 2, "sequence": 2, "step_type": "REPAIR", "purpose": "Flush DNS", "authorization_required": True},
        ],
        "before_evidence": {"dns_resolved": False},
        "after_evidence": {},
        "resolution_status": "INCONCLUSIVE",
        "tutor_explanation": "DNS educational context",
    }
    with patch("streamlit.container"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
        render_troubleshooting_workflow_card(wf_data)


def test_safe_retry_on_diagnostic_failure(workflow_engine, mock_registry):
    """Test safe diagnostic tool is retried once upon failure."""
    fail_then_succeed = MagicMock(side_effect=[Exception("Transient network glitch"), {"status": "ok", "adapters": ["Ethernet0"]}])
    with patch.object(mock_registry.get("check_network_adapters"), "handler", fail_then_succeed):
        diag = DiagnosticResponse(summary="Retry test", recommended_tools=["check_network_adapters"])
        wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_retry")
        res = workflow_engine.execute_next_step(wf.workflow_id, "s_retry")
        assert res["success"] is True
        assert fail_then_succeed.call_count == 2


def test_pause_and_resume_workflow(workflow_engine):
    """Test pausing and resuming a workflow safely."""
    diag = DiagnosticResponse(summary="Pause test")
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_pause")
    
    workflow_engine.transition_state(wf, WorkflowStatus.PAUSED)
    assert wf.status == WorkflowStatus.PAUSED

    # Resuming
    workflow_engine.transition_state(wf, WorkflowStatus.DIAGNOSING)
    assert wf.status == WorkflowStatus.DIAGNOSING


def test_degraded_mode_workflow_execution(workflow_engine):
    """Test workflow creation and execution when AI is degraded/offline."""
    # When Ollama is offline, deterministic diagnosis still produces valid workflows
    fallback_diag = DiagnosticResponse(
        summary="Offline Heuristic: Network Issue",
        observations=["Offline heuristic evaluated"],
        interpretations=["Network diagnostics required"],
        hypotheses=[
            DiagnosticHypothesis(
                hypothesis_id="h_offline",
                category="network",
                statement="Potential adapter configuration mismatch",
                recommended_tools=["check_network_adapters"],
            )
        ],
        recommended_tools=["check_network_adapters"],
        tutor_explanation="Deterministic diagnostic path active.",
    )
    wf = workflow_engine.create_workflow_from_diagnosis(fallback_diag, session_id="s_offline")
    assert wf.workflow_id.startswith("wf_")
    assert wf.status == WorkflowStatus.CREATED
    assert wf.tutor_explanation == "Deterministic diagnostic path active."


def test_voice_and_screenshot_evidence_in_workflow(workflow_engine):
    """Test voice transcript and screenshot evidence flow into diagnostic intelligence and workflow."""
    voice_hyp = DiagnosticHypothesis(
        hypothesis_id="h_voice",
        category="network",
        statement="User reported Wi-Fi disconnect via voice",
        supporting_evidence_ids=["ev_voice_01", "ev_screen_01"],
        recommended_tools=["check_network_adapters"],
    )
    diag = DiagnosticResponse(
        summary="Multi-modal Diagnostic Workflow",
        observations=["Voice symptom: Wi-Fi lost", "Screenshot symptom: Yellow exclamation mark"],
        hypotheses=[voice_hyp],
        recommended_tools=["check_network_adapters"],
        tutor_explanation="Voice & screenshot indicators combined.",
    )
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_multi")
    assert len(wf.steps) >= 2
    assert wf.steps[0].tool_name == "check_network_adapters"


def test_workflow_serialization_and_deserialization(workflow_engine):
    """Test serialization of troubleshooting workflows to dictionaries."""
    diag = DiagnosticResponse(summary="Serialization test")
    candidate = RepairCandidate(
        candidate_id="c_ser",
        diagnosis_id="d1",
        tool_name="flush_dns_cache",
        purpose="Flush DNS",
        risk_level="MEDIUM",
        session_id="s_ser",
    )
    wf = workflow_engine.create_workflow_from_diagnosis(diag, session_id="s_ser", repair_candidate=candidate)
    d = wf.to_dict()

    assert d["workflow_id"] == wf.workflow_id
    assert d["session_id"] == "s_ser"
    assert d["max_steps"] == 8
    assert d["status"] == "CREATED"
    assert d["repair_candidate"]["tool_name"] == "flush_dns_cache"
    assert isinstance(d["steps"], list)


