"""WinFix AI — Session Isolation & Boundary Tests (Phase 33)."""

import pytest
from tests.reliability.fixtures import MockTelemetryDB
from tests.reliability.assertions import assert_session_isolated
from production.telemetry import TelemetryService
from production.telemetry_models import TelemetryEventType
from agent.checkpoint_manager import CheckpointManager
from agent.evidence_models import EvidenceItem, EvidenceStore, EvidenceType, EvidenceQuality, EvidenceSource, EvidenceStatus
from agent.idempotency import IdempotencyEngine


def test_cross_session_telemetry_isolation():
    """Verify session A cannot see session B telemetry events."""
    db = MockTelemetryDB()
    service = TelemetryService(db_manager=db)

    service.record_session_event("sess_alpha", TelemetryEventType.SESSION_STARTED)
    service.record_workflow_event("sess_alpha", TelemetryEventType.WORKFLOW_STARTED, domain="NETWORK")

    service.record_session_event("sess_beta", TelemetryEventType.SESSION_STARTED)
    service.record_workflow_event("sess_beta", TelemetryEventType.WORKFLOW_COMPLETED, domain="STORAGE")

    events_alpha = service.get_events(session_id="sess_alpha")
    events_beta = service.get_events(session_id="sess_beta")

    assert len(events_alpha) == 2
    assert len(events_beta) == 2

    assert_session_isolated(events_alpha, "sess_beta")
    assert_session_isolated(events_beta, "sess_alpha")


def test_cross_session_evidence_isolation():
    """Verify session A cannot read evidence collected for session B."""
    store = EvidenceStore()
    item_b = EvidenceItem(
        evidence_id="ev_b_01",
        session_id="sess_b",
        evidence_type=EvidenceType.NETWORK,
        source=EvidenceSource.WINDOWS_TOOL,
        category="network",
        observation="Adapter connected",
        value={"adapter": "Wi-Fi", "connected": True},
        quality=EvidenceQuality.VERIFIED,
        status=EvidenceStatus.VALID,
    )
    store.add_evidence(item_b)

    evidence_for_a = store.get_session_evidence(session_id="sess_a")
    assert len(evidence_for_a) == 0


def test_cross_session_checkpoint_isolation():
    """Verify checkpoints cannot be loaded across session boundaries."""
    db = MockTelemetryDB()
    chk_mgr = CheckpointManager(db_manager=db)

    chk_mgr.create_checkpoint(
        session_id="sess_owner",
        workflow_id="wf_owner",
        step_id=1,
        workflow_state="DIAGNOSING",
        current_step_index=0,
        domain="SERVICES",
    )

    chk_other = chk_mgr.get_latest_checkpoint_for_session("sess_intruder")
    assert chk_other is None


def test_cross_session_idempotency_isolation():
    """Verify idempotency hashes in session A do not block legitimate executions in session B."""
    engine = IdempotencyEngine()

    rec_a = engine.record_execution_start(
        session_id="sess_1",
        workflow_id="wf_1",
        step_id=1,
        tool_name="flush_dns_cache",
        arguments={},
        confirmation_token="auth_tok_1",
    )
    assert rec_a is not None

    status_b, _ = engine.evaluate_idempotency(
        session_id="sess_2",
        workflow_id="wf_2",
        tool_name="flush_dns_cache",
        arguments={},
    )
    # Different session must be evaluated as UNIQUE
    assert status_b.value == "UNIQUE"
