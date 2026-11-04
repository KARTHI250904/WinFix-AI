"""WinFix AI — Phase 31 Resume Engine Unit Tests.

Validates:
1. Terminal state resumption rejection (RESOLVED, CANCELLED, FAILED)
2. Stale checkpoint detection triggering revalidation
3. Interrupted repair evaluation: Revalidation instead of blind replay
4. Interrupted repair with confirmed resolved telemetry
5. Diagnostic sequence resumption
6. Reauthorization requirements on ambiguous recovery
"""

from datetime import datetime, timedelta, timezone
import pytest

from agent.recovery_models import Checkpoint, ResumeAction
from agent.resume_engine import ResumeEngine
from agent.verification_registry import VerificationRegistry


class TestResumeEngine:
    """Test suite for ResumeEngine evaluation logic."""

    @pytest.fixture
    def engine(self):
        return ResumeEngine()

    def test_resume_null_checkpoint(self, engine):
        decision = engine.evaluate_resumption(None)
        assert decision.action == ResumeAction.FAILED
        assert "No valid checkpoint" in decision.rationale

    def test_resume_terminal_state_cancelled(self, engine):
        chk = Checkpoint(
            checkpoint_id="chk-term-1",
            session_id="s1",
            workflow_id="w1",
            step_id=3,
            workflow_state="CANCELLED",
            current_step_index=3,
            domain="SERVICES",
        )
        decision = engine.evaluate_resumption(chk)
        assert decision.action == ResumeAction.CANCEL
        assert "terminal state" in decision.rationale

    def test_resume_stale_checkpoint_triggers_revalidation(self, engine):
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
        chk = Checkpoint(
            checkpoint_id="chk-stale-1",
            session_id="s1",
            workflow_id="w1",
            step_id=2,
            workflow_state="DIAGNOSING",
            current_step_index=2,
            domain="NETWORK",
            updated_at=old_time,
        )
        decision = engine.evaluate_resumption(chk)
        assert decision.action == ResumeAction.REVALIDATE
        assert decision.requires_reauthorization is True
        assert "stale" in decision.rationale

    def test_resume_interrupted_repair_requires_revalidation(self, engine):
        """CRITICAL INVARIANT: Incomplete repair MUST trigger revalidation, NOT repair replay."""
        chk = Checkpoint(
            checkpoint_id="chk-repair-1",
            session_id="s1",
            workflow_id="w1",
            step_id=4,
            workflow_state="REPAIRING",
            current_step_index=4,
            domain="NETWORK",
            repair_candidate={"tool_name": "flush_dns_cache"},
            execution_state={"dns_resolved": False},
        )
        decision = engine.evaluate_resumption(chk, live_telemetry=None)

        assert decision.action == ResumeAction.REVALIDATE
        assert decision.requires_reauthorization is True
        assert decision.target_tool == "check_dns_resolution"
        assert "interrupted during/after repair 'flush_dns_cache'" in decision.rationale.lower()


    def test_resume_interrupted_repair_with_resolved_telemetry(self, engine):
        """If live telemetry verifies the issue is already resolved, resume cleanly without repair replay."""
        chk = Checkpoint(
            checkpoint_id="chk-repair-2",
            session_id="s1",
            workflow_id="w1",
            step_id=4,
            workflow_state="VERIFYING",
            current_step_index=4,
            domain="NETWORK",
            repair_candidate={"tool_name": "flush_dns_cache"},
            execution_state={"dns_resolved": False},
        )
        # Telemetry collected on recovery showing DNS is now resolved
        live_telemetry = {"dns_resolved": True, "success": True}

        decision = engine.evaluate_resumption(chk, live_telemetry=live_telemetry)
        assert decision.action == ResumeAction.RESUME
        assert decision.requires_reauthorization is False
        assert "confirmed issue resolved" in decision.rationale

    def test_resume_diagnostic_state(self, engine):
        """Interrupted during safe diagnosis resumes diagnostic sequence."""
        chk = Checkpoint(
            checkpoint_id="chk-diag-1",
            session_id="s1",
            workflow_id="w1",
            step_id=1,
            workflow_state="DIAGNOSING",
            current_step_index=1,
            domain="STORAGE",
        )
        decision = engine.evaluate_resumption(chk)
        assert decision.action == ResumeAction.RESUME
        assert decision.safe_step_index == 1
        assert decision.requires_reauthorization is False
