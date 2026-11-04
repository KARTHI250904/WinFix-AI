"""WinFix AI — Recovery Stress & Interruption Tests (Phase 33)."""

import pytest
from agent.recovery_manager import RecoveryManager
from agent.checkpoint_manager import CheckpointManager
from agent.resume_engine import ResumeEngine
from agent.recovery_models import Checkpoint, RecoveryState, ResumeAction


def test_repeated_crash_and_resume_cycles():
    """Simulate 20 repeated crash-and-resume cycles on interrupted repairs."""
    chk_mgr = CheckpointManager(db_manager=None)
    resume_eng = ResumeEngine()
    rec_mgr = RecoveryManager(checkpoint_manager=chk_mgr, resume_engine=resume_eng)

    for i in range(20):
        sess_id = f"crash_sess_{i:02d}"
        wf_id = f"wf_crash_{i:02d}"

        # Checkpoint created during repair execution
        rec_mgr.record_checkpoint(
            session_id=sess_id,
            workflow_id=wf_id,
            step_id=3,
            workflow_state="REPAIRING",
            current_step_index=2,
            domain="NETWORK",
            repair_candidate={"tool_name": "flush_dns_cache", "arguments": {}},
        )

        # Interruption occurs -> System restarts and recovers
        res = rec_mgr.recover_session(session_id=sess_id)
        assert res.state in (RecoveryState.REVALIDATING, RecoveryState.RESUMABLE, RecoveryState.AUTHORIZATION_REQUIRED)
        # MUST NEVER blindly replay flush_dns_cache
        assert res.decision.action != ResumeAction.RESUME or res.decision.target_step_type != "REPAIR"


def test_stale_checkpoint_revalidation_enforced():
    """Verify that stale checkpoints require revalidation and cannot resume old repairs."""
    chk_mgr = CheckpointManager(db_manager=None)
    resume_eng = ResumeEngine()

    chk = chk_mgr.create_checkpoint(
        session_id="sess_stale_01",
        workflow_id="wf_stale_01",
        step_id=2,
        workflow_state="DIAGNOSING",
        current_step_index=1,
        domain="PERFORMANCE",
    )

    # Create stale checkpoint with timestamp from 2020
    stale_chk = Checkpoint(
        checkpoint_id=chk.checkpoint_id,
        session_id=chk.session_id,
        workflow_id=chk.workflow_id,
        step_id=chk.step_id,
        workflow_state=chk.workflow_state,
        current_step_index=chk.current_step_index,
        domain=chk.domain,
        created_at="2020-01-01T00:00:00+00:00",
        updated_at="2020-01-01T00:00:00+00:00",
    )
    decision = resume_eng.evaluate_resumption(stale_chk)
    assert decision.action == ResumeAction.REVALIDATE
    assert "stale" in decision.rationale.lower()
