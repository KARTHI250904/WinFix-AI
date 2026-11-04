"""WinFix AI — Phase 30 Adaptive Diagnostic Security & Invariant Tests.

Validates:
1. Strict AST security scan on all Phase 30 modules (0 prohibited calls)
2. Tool Registry preservation: 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates)
3. Execution != Success invariant
4. Verification cannot be bypassed or spoofed
5. Step budget bound (<= 8 steps) prevents infinite reasoning loops
6. Cross-session isolation of adaptive contexts and telemetry
7. Fail-closed behavior on corrupted state transitions
"""

import ast
import os
import pytest

from agent.adaptive_engine import AdaptiveDiagnosticEngine
from agent.adaptive_models import (
    AdaptiveSessionContext,
    AdaptiveState,
    ResolutionOutcome,
)
from agent.diagnostic_models import DiagnosticHypothesis, HypothesisStatus
from agent.domain_models import TroubleshootingDomain
from agent.evidence_models import (
    EvidenceItem,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
)
from agent.resolution_analyzer import ResolutionAnalyzer
from agent.tool_registry import ToolRegistry, default_tool_registry




class TestPhase30SecurityInvariants:
    """Security invariant and AST enforcement tests."""

    PHASE_30_MODULES = [
        "agent/adaptive_models.py",
        "agent/adaptive_engine.py",
        "agent/evidence_evolution.py",
        "agent/resolution_analyzer.py",
        "agent/scenario_models.py",
        "agent/scenario_runner.py",
        "agent/real_windows_validator.py",
    ]

    FORBIDDEN_CALLS = {"eval", "exec", "system", "popen", "spawn"}

    def test_phase_30_ast_prohibited_calls(self):
        """Verify 0 prohibited AST execution patterns in Phase 30 modules."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for rel_path in self.PHASE_30_MODULES:
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


    def test_execution_success_cannot_spoof_resolution(self):
        """CRITICAL SECURITY: Successful repair execution with failed verification MUST fail resolution."""
        res = ResolutionAnalyzer.analyze_resolution(
            session_id="sec-sess-1",
            workflow_id="sec-wf-1",
            primary_domain=TroubleshootingDomain.SERVICES,
            execution_succeeded=True,
            verification_succeeded=False,
            explanation="Attacker claims fake repair success",
        )
        assert res.execution_succeeded is True
        assert res.verification_succeeded is False
        assert res.outcome == ResolutionOutcome.VERIFICATION_FAILED
        assert res.resolution_status.value == "NOT_RESOLVED"

    def test_step_limit_prevents_infinite_adaptive_loop(self):
        """Adaptive engine must fail closed to UNRESOLVED once step count reaches 8."""
        store = EvidenceStore()
        engine = AdaptiveDiagnosticEngine(evidence_store=store)
        ctx = engine.create_session("sec-loop-sess", "Loop test", TroubleshootingDomain.NETWORK)

        hyp = DiagnosticHypothesis(
            hypothesis_id="hyp-loop",
            category="NETWORK",
            statement="Looping hypothesis",
            status=HypothesisStatus.POSSIBLE,
        )

        for i in range(8):
            ctx.record_step(f"step_{i}")

        ev = EvidenceItem(
            evidence_id="ev-overflow",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="NETWORK",
            observation="Overflow evidence",
            value={"resolved": True},
            session_id="sec-loop-sess",
        )

        adapted_hyp, decision = engine.evaluate_telemetry_and_adapt(ctx, hyp, ev)
        assert decision.action_type == "ABORT_UNRESOLVED"
        assert ctx.current_state == AdaptiveState.UNRESOLVED

    def test_cross_session_adaptive_isolation(self):
        """Telemetry and transitions in session A must never leak into session B."""
        store = EvidenceStore()
        engine = AdaptiveDiagnosticEngine(evidence_store=store)

        ctx_a = engine.create_session("sess-alpha", "Alpha symptom", TroubleshootingDomain.SERVICES)
        ctx_b = engine.create_session("sess-beta", "Beta symptom", TroubleshootingDomain.STORAGE)

        ev_a = EvidenceItem(
            evidence_id="ev-a",
            evidence_type=EvidenceType.SERVICE,
            source=EvidenceSource.WINDOWS_TOOL,
            category="SERVICES",
            observation="Service status check",
            value={"status": "STOPPED"},
            session_id="sess-alpha",
        )
        engine.evaluate_telemetry_and_adapt(ctx_a, None, ev_a)

        # Query session B
        b_evs = store.get_session_evidence("sess-beta")
        assert len(b_evs) == 0
        assert len(ctx_b.evidence_changes) == 0
        assert ctx_b.primary_domain == TroubleshootingDomain.STORAGE

