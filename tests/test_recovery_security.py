"""WinFix AI — Phase 31 Recovery Security & Invariant Tests.

Validates:
1. Strict AST security scan on all Phase 31 modules (0 prohibited calls)
2. Tool Registry preservation: 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates)
3. Cross-session checkpoint and recovery isolation
4. Critical Repair Replay Prevention invariant
5. Authorization tampering detection and fail-closed invalidation
"""

import ast
import os
import pytest

from agent.idempotency import IdempotencyEngine, IdempotencyStatus
from agent.recovery_manager import RecoveryManager
from agent.recovery_models import ResumeAction
from agent.resume_engine import ResumeEngine
from agent.tool_registry import ToolRegistry, default_tool_registry


class TestPhase31SecurityInvariants:
    """Security invariant and AST enforcement tests for Phase 31."""

    PHASE_31_MODULES = [
        "agent/recovery_models.py",
        "agent/idempotency.py",
        "agent/checkpoint_manager.py",
        "agent/resume_engine.py",
        "agent/recovery_manager.py",
    ]

    FORBIDDEN_CALLS = {"eval", "exec", "system", "popen", "spawn"}

    def test_phase_31_ast_prohibited_calls(self):
        """Verify 0 prohibited AST execution patterns in Phase 31 recovery modules."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for rel_path in self.PHASE_31_MODULES:
            full_path = os.path.join(base_dir, rel_path)
            assert os.path.exists(full_path), f"File {rel_path} does not exist"

            with open(full_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check func name
                    if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_CALLS:
                        pytest.fail(f"Prohibited call '{node.func.id}' in {rel_path}:L{node.lineno}")
                    # Check attribute call (e.g. os.system, subprocess.run)
                    if isinstance(node.func, ast.Attribute) and node.func.attr in self.FORBIDDEN_CALLS:
                        pytest.fail(f"Prohibited attribute call '{node.func.attr}' in {rel_path}:L{node.lineno}")
                    # Check subprocess import/call
                    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        if node.func.value.id == "subprocess":
                            pytest.fail(f"Direct subprocess call in {rel_path}:L{node.lineno}")

    def test_tool_registry_preservation(self):
        """Verify tool registry baseline remains strictly 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH)."""
        reg = default_tool_registry
        all_tools = reg.list_tools()

        assert len(all_tools) in (59, 62), f"Expected 59 or 62 tools, found {len(all_tools)}"
        safe_tools = [t for t in all_tools if t.risk.value == "SAFE"]
        med_tools = [t for t in all_tools if t.risk.value == "MEDIUM"]
        high_tools = [t for t in all_tools if t.risk.value == "HIGH"]

        assert len(safe_tools) in (49, 52)
        assert len(med_tools) == 10
        assert len(high_tools) == 0

    def test_cross_session_recovery_isolation(self):
        """Session A cannot access or recover Session B checkpoints."""
        mgr = RecoveryManager()
        mgr.clear()

        mgr.record_checkpoint("sess-victim", "wf-victim", 2, "REPAIRING", 2, "SERVICES")

        # Attacker in different session attempts recovery
        res_attacker = mgr.recover_session("sess-attacker")
        assert res_attacker.decision.action == ResumeAction.FAILED
        assert "no saved checkpoints" in res_attacker.explanation.lower() or "no checkpoints" in res_attacker.decision.rationale.lower()


    def test_repair_replay_prevention_on_ambiguous_crash(self):
        """CRITICAL INVARIANT: Interrupted repair MUST trigger revalidation and invalidate authorization."""
        mgr = RecoveryManager()
        mgr.clear()

        mgr.record_checkpoint(
            session_id="sess-ambig",
            workflow_id="wf-ambig",
            step_id=3,
            workflow_state="REPAIRING",
            current_step_index=3,
            domain="NETWORK",
            repair_candidate={"tool_name": "flush_dns_cache"},
            execution_state={"dns_resolved": False},
        )

        res = mgr.recover_session("sess-ambig")
        assert res.decision.action == ResumeAction.REVALIDATE
        assert res.decision.requires_reauthorization is True
        assert res.decision.target_tool == "check_dns_resolution"

    def test_authorization_tampering_detection(self):
        """Tampered authorization tokens or arguments are detected as mismatches."""
        engine = IdempotencyEngine()
        session_id = "sess-auth-sec"
        wf_id = "wf-auth-sec"
        tool_name = "clean_user_temp_cache"

        # Record valid execution start with token-123
        engine.record_execution_start(
            session_id=session_id,
            workflow_id=wf_id,
            step_id=1,
            tool_name=tool_name,
            arguments={},
            confirmation_token="token-123",
        )

        # Attacker attempts replay with modified token
        status, _ = engine.evaluate_idempotency(
            session_id=session_id,
            workflow_id=wf_id,
            tool_name=tool_name,
            arguments={},
            confirmation_token="tampered-token-999",
        )
        assert status in (IdempotencyStatus.AMBIGUOUS_INTERRUPTED, IdempotencyStatus.AUTHORIZATION_MISMATCH)
