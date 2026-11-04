"""WinFix AI — Phase 31 Recovery Manager & Lifecycle Tests.

Validates:
1. End-to-end session recovery flow
2. Fail-closed behavior on missing checkpoints
3. Audit trail generation for all recovery events
4. Explicit recovery cancellation
5. Interrupted repair state revalidation with live telemetry
6. Recovery event isolation by session
"""

import pytest

from agent.recovery_manager import RecoveryManager
from agent.recovery_models import (
    RecoveryEventType,
    RecoveryState,
    ResumeAction,
)


class TestRecoveryManager:
    """Test suite for the RecoveryManager orchestrator."""

    @pytest.fixture
    def manager(self):
        mgr = RecoveryManager()
        mgr.clear()
        return mgr

    def test_recovery_no_checkpoints_fails_closed(self, manager):
        result = manager.recover_session("non-existent-session")
        assert result.state == RecoveryState.FAILED
        assert result.decision.action == ResumeAction.FAILED
        assert "no saved checkpoints" in result.explanation.lower() or "no checkpoints" in result.decision.rationale.lower()


    def test_recovery_interrupted_repair_flow(self, manager):
        session_id = "sess-recov-1"
        wf_id = "wf-recov-1"

        # 1. Create checkpoint during repair
        manager.record_checkpoint(
            session_id=session_id,
            workflow_id=wf_id,
            step_id=3,
            workflow_state="REPAIRING",
            current_step_index=3,
            domain="SERVICES",
            repair_candidate={"tool_name": "restart_service", "arguments": {"service_name": "wuauserv"}},
            execution_state={"state": "stopped"},
        )

        # 2. Trigger recovery without live telemetry
        res = manager.recover_session(session_id)
        assert res.state == RecoveryState.REVALIDATING
        assert res.decision.action == ResumeAction.REVALIDATE
        assert res.decision.requires_reauthorization is True

        # 3. Verify event audit trail
        events = manager.get_recovery_events(session_id)
        assert len(events) >= 2
        event_types = [e.event_type for e in events]
        assert RecoveryEventType.CHECKPOINT_CREATED.value in event_types
        assert RecoveryEventType.RECOVERY_STARTED.value in event_types
        assert RecoveryEventType.STATE_REVALIDATED.value in event_types

    def test_recovery_with_live_resolved_telemetry(self, manager):
        session_id = "sess-recov-2"
        wf_id = "wf-recov-2"

        # Checkpoint in VERIFYING state
        manager.record_checkpoint(
            session_id=session_id,
            workflow_id=wf_id,
            step_id=4,
            workflow_state="VERIFYING",
            current_step_index=4,
            domain="SERVICES",
            repair_candidate={"tool_name": "restart_service", "arguments": {"service_name": "wuauserv"}},
            execution_state={"state": "stopped"},
        )

        # Live telemetry shows service is now running
        live_telemetry = {"state": "running", "success": True}

        res = manager.recover_session(session_id, live_telemetry=live_telemetry)
        assert res.state == RecoveryState.RESUMABLE
        assert res.decision.action == ResumeAction.RESUME
        assert res.decision.requires_reauthorization is False

    def test_recovery_explicit_cancellation(self, manager):
        session_id = "sess-cancel-1"
        wf_id = "wf-cancel-1"

        res = manager.cancel_recovery(session_id, wf_id)
        assert res.state == RecoveryState.CANCELLED
        assert res.decision.action == ResumeAction.CANCEL

        events = manager.get_recovery_events(session_id)
        assert any(e.event_type == RecoveryEventType.WORKFLOW_CANCELLED.value for e in events)

    def test_recovery_event_session_isolation(self, manager):
        manager.record_checkpoint("sess-A", "wf-A", 1, "DIAGNOSING", 1, "NETWORK")
        manager.record_checkpoint("sess-B", "wf-B", 1, "STORAGE", 1, "STORAGE")

        events_a = manager.get_recovery_events("sess-A")
        events_b = manager.get_recovery_events("sess-B")

        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0].session_id == "sess-A"
        assert events_b[0].session_id == "sess-B"
