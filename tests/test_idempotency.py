"""WinFix AI — Phase 31 Idempotency & Replay Protection Unit Tests.

Validates:
1. Canonical argument hashing
2. Exact authorization binding verification
3. Case A: Duplicate execution detection
4. Case B: Different argument detection
5. Case C: Cross-session execution isolation
6. Case D: Interrupted execution / ambiguous replay protection
7. Authorization mismatch detection
"""

import pytest

from agent.idempotency import IdempotencyEngine, IdempotencyStatus


class TestIdempotencyEngine:
    """Test suite for idempotency evaluations and replay prevention."""

    @pytest.fixture
    def engine(self):
        return IdempotencyEngine()

    def test_argument_hash_stability(self):
        """Canonical JSON sorting ensures identical hash regardless of dictionary insertion order."""
        args_1 = {"b": 2, "a": 1, "nested": {"y": 20, "x": 10}}
        args_2 = {"a": 1, "b": 2, "nested": {"x": 10, "y": 20}}

        hash_1 = IdempotencyEngine.compute_argument_hash("flush_dns_cache", args_1)
        hash_2 = IdempotencyEngine.compute_argument_hash("flush_dns_cache", args_2)

        assert hash_1 == hash_2
        assert len(hash_1) == 64

    def test_authorization_hash_binding(self):
        """Authorization hash binds session, workflow, tool, argument hash, and confirmation token."""
        auth_1 = IdempotencyEngine.compute_authorization_hash(
            session_id="sess-1",
            workflow_id="wf-1",
            tool_name="restart_service",
            arguments={"service_name": "wuauserv"},
            confirmation_token="token-abc",
        )
        auth_2 = IdempotencyEngine.compute_authorization_hash(
            session_id="sess-1",
            workflow_id="wf-1",
            tool_name="restart_service",
            arguments={"service_name": "wuauserv"},
            confirmation_token="token-abc",
        )
        auth_diff_token = IdempotencyEngine.compute_authorization_hash(
            session_id="sess-1",
            workflow_id="wf-1",
            tool_name="restart_service",
            arguments={"service_name": "wuauserv"},
            confirmation_token="token-different",
        )

        assert auth_1 == auth_2
        assert auth_1 != auth_diff_token

    def test_case_a_duplicate_succeeded(self, engine):
        """Same tool, session, workflow, and arguments returns DUPLICATE_SUCCEEDED."""
        session_id = "sess-dup-1"
        wf_id = "wf-dup-1"
        tool_name = "flush_dns_cache"
        args = {}

        rec = engine.record_execution_start(session_id, wf_id, 1, tool_name, args)
        engine.record_execution_complete(rec.execution_id, success=True)

        status, found = engine.evaluate_idempotency(session_id, wf_id, tool_name, args)
        assert status == IdempotencyStatus.DUPLICATE_SUCCEEDED
        assert found is not None
        assert found.execution_id == rec.execution_id

    def test_case_b_different_arguments(self, engine):
        """Same tool, session, workflow, but different arguments returns DIFFERENT_ARGUMENTS."""
        session_id = "sess-args-1"
        wf_id = "wf-args-1"
        tool_name = "restart_service"

        rec = engine.record_execution_start(session_id, wf_id, 1, tool_name, {"service_name": "wuauserv"})
        engine.record_execution_complete(rec.execution_id, success=True)

        status, _ = engine.evaluate_idempotency(session_id, wf_id, tool_name, {"service_name": "bthserv"})
        assert status == IdempotencyStatus.DIFFERENT_ARGUMENTS

    def test_case_c_cross_session_isolation(self, engine):
        """Same tool and args in a different session returns UNIQUE."""
        tool_name = "clean_user_temp_cache"
        args = {}

        rec_a = engine.record_execution_start("session-alpha", "wf-alpha", 1, tool_name, args)
        engine.record_execution_complete(rec_a.execution_id, success=True)

        status, _ = engine.evaluate_idempotency("session-beta", "wf-beta", tool_name, args)
        assert status == IdempotencyStatus.UNIQUE

    def test_case_d_interrupted_execution_replay_blocked(self, engine):
        """In-progress execution that was not completed returns AMBIGUOUS_INTERRUPTED."""
        session_id = "sess-crash-1"
        wf_id = "wf-crash-1"
        tool_name = "restart_defender_service"
        args = {}

        # Started but never completed (simulating app crash)
        rec = engine.record_execution_start(session_id, wf_id, 2, tool_name, args)

        status, found = engine.evaluate_idempotency(session_id, wf_id, tool_name, args)
        assert status == IdempotencyStatus.AMBIGUOUS_INTERRUPTED
        assert found is not None
        assert found.execution_status == "STARTED"
