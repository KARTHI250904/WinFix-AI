"""WinFix AI — Authorization Stress & Token Invalidation Tests (Phase 33)."""

import pytest
from agent.safety import default_safety_engine
from agent.idempotency import IdempotencyEngine, IdempotencyStatus
from modes.autopilot import compute_plan_hash


def test_mutated_arguments_invalidate_authorization():
    """Verify modifying tool arguments invalidates previously granted authorization."""
    engine = IdempotencyEngine()

    token = "valid_sha256_token_123"
    rec = engine.record_execution_start(
        session_id="sess_auth",
        workflow_id="wf_auth",
        step_id=1,
        tool_name="clean_temp_files",
        arguments={"safe_path": "C:\\temp"},
        confirmation_token=token,
    )
    assert rec is not None

    # Mutated arguments check
    status, _ = engine.evaluate_idempotency(
        session_id="sess_auth",
        workflow_id="wf_auth",
        tool_name="clean_temp_files",
        arguments={"safe_path": "C:\\Windows\\System32"},  # Mutated!
    )
    # Different arguments must match DIFFERENT_ARGUMENTS
    assert status == IdempotencyStatus.DIFFERENT_ARGUMENTS


def test_autopilot_plan_hash_tampering_blocked():
    """Verify that tampering with an Autopilot plan steps alters plan hash."""
    steps_1 = [{"sequence": 1, "tool_name": "check_dns_resolution", "arguments": {}}]
    steps_2 = [{"sequence": 1, "tool_name": "flush_dns_cache", "arguments": {}}]

    hash_1 = compute_plan_hash(steps_1, "sess_01")
    hash_2 = compute_plan_hash(steps_2, "sess_01")

    assert hash_1 != hash_2
