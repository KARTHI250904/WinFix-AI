"""WinFix AI — Verification Stress & Non-Equivalence Tests (Phase 33)."""

import pytest
from agent.workflow_models import ResolutionStatus
from agent.workflow_engine import DeterministicResolutionEngine


def test_execution_success_with_failed_verification():
    """Verify that a successful tool return does NOT imply resolution if verification fails."""
    before_state = {"status": "unhealthy", "dns_resolved": False}
    # Repair tool succeeded, but verification measurement shows DNS still not resolved
    after_state = {"status": "unhealthy", "dns_resolved": False}

    status, explanation = DeterministicResolutionEngine.compare_evidence(before_state, after_state)
    assert status == ResolutionStatus.NOT_RESOLVED
    assert "continues to fail" in explanation.lower() or "not resolved" in explanation.lower()


def test_inconclusive_verification_on_missing_after_telemetry():
    """Verify incomplete verification signals produce INCONCLUSIVE, not false positive resolution."""
    before_state = {"status": "error"}
    after_state = {}  # Incomplete/empty measurement

    status, explanation = DeterministicResolutionEngine.compare_evidence(before_state, after_state)
    assert status == ResolutionStatus.INCONCLUSIVE
    assert "insufficient" in explanation.lower()
