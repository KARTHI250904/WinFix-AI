"""WinFix AI — Reliability Stress & Workload Tests (Phase 33)."""

import pytest
from tests.reliability.fixtures import MockTelemetryDB
from tests.reliability.stress_runner import StressTestRunner
from tests.reliability.assertions import assert_security_invariants
from production.telemetry import TelemetryService
from production.telemetry_analytics import TelemetryAnalytics
from agent.recovery_manager import RecoveryManager
from agent.checkpoint_manager import CheckpointManager


def test_100_session_stress_workload():
    """Execute a 100-session workload and verify all metrics and invariants."""
    db = MockTelemetryDB()
    telemetry = TelemetryService(db_manager=db)
    chk_mgr = CheckpointManager(db_manager=db)
    rec_mgr = RecoveryManager(checkpoint_manager=chk_mgr)

    runner = StressTestRunner(telemetry_service=telemetry, recovery_manager=rec_mgr)
    results = runner.run_multi_session_stress(num_sessions=100, events_per_session=5)

    assert results["sessions_created"] == 100
    assert results["checkpoints_created"] == 100
    assert results["total_events"] == 500

    # Analytics aggregation over 100 sessions
    analytics = TelemetryAnalytics(telemetry_service=telemetry)
    summary = analytics.get_workflow_summary(limit=1000)
    assert summary["completed"] == 90
    assert summary["cancelled"] == 10

    assert_security_invariants()


def test_checkpoint_consistency_under_rapid_updates():
    """Verify that multiple rapid checkpoint updates for a single session maintain integrity."""
    db = MockTelemetryDB()
    chk_mgr = CheckpointManager(db_manager=db)
    rec_mgr = RecoveryManager(checkpoint_manager=chk_mgr)

    sess_id = "rapid_sess_01"
    wf_id = "wf_rapid_01"

    for step in range(1, 9):
        rec_mgr.record_checkpoint(
            session_id=sess_id,
            workflow_id=wf_id,
            step_id=step,
            workflow_state="DIAGNOSING" if step < 5 else "VERIFYING",
            current_step_index=step - 1,
            domain="NETWORK",
            evidence_references=[f"ev_{step}"],
        )

    latest = chk_mgr.get_latest_checkpoint_for_session(sess_id)
    assert latest is not None
    assert latest.step_id == 8
    assert latest.current_step_index == 7
    assert latest.workflow_state == "VERIFYING"
