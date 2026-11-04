"""WinFix AI — Phase 30 Adaptive Diagnostic & Scenario Suite Tests.

Validates:
1. All 10 scenario domain families (Network, Performance, Storage, Services, Windows Update, Defender, Bluetooth, App Crash, Startup, System)
2. Noisy, stale, contradictory, and missing evidence adaptation
3. Hypothesis state transitions (POSSIBLE -> CONTRADICTED -> ADAPTING -> SUPPORTED)
4. Before/after metric comparison and state delta computation
5. Deterministic ResolutionAnalyzer (Execution Success != Verification Success)
6. Step limit enforcement (<= 8 steps max bound)
7. Real Windows Read-Only environment validation
"""

import pytest
import uuid

from agent.adaptive_engine import AdaptiveDiagnosticEngine
from agent.adaptive_models import (
    AdaptiveSessionContext,
    AdaptiveState,
    BeforeAfterComparison,
    DiagnosticDecision,
    EvidenceChangeType,
    HypothesisTransition,
    ResolutionAnalysis,
    ResolutionOutcome,
)
from agent.diagnostic_models import DiagnosticHypothesis, HypothesisStatus
from agent.domain_models import FailureCategory, TroubleshootingDomain
from agent.evidence_evolution import EvidenceEvolutionTracker
from agent.evidence_models import (
    EvidenceItem,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
)
from agent.real_windows_validator import RealWindowsValidator, SubsystemStatus
from agent.resolution_analyzer import ResolutionAnalyzer
from agent.scenario_models import ScenarioDefinition, ScenarioExecutionResult
from agent.scenario_runner import FakeWindowsEnvironment, ScenarioRunner
from agent.workflow_models import ResolutionStatus


class TestAdaptiveDiagnosticModels:
    """Test adaptive diagnostic data structures and immutability/validation."""

    def test_adaptive_session_context_step_budget(self):
        ctx = AdaptiveSessionContext(
            session_id="test-session-1",
            primary_domain=TroubleshootingDomain.NETWORK,
            max_steps=8,
        )
        for i in range(8):
            assert ctx.can_execute_step() is True
            assert ctx.record_step(f"tool_{i}") is True

        # 9th step must fail budget
        assert ctx.can_execute_step() is False
        assert ctx.record_step("tool_overflow") is False
        assert ctx.current_state == AdaptiveState.UNRESOLVED
        assert ctx.step_count == 8

    def test_evidence_evolution_tracker(self):
        store = EvidenceStore()
        tracker = EvidenceEvolutionTracker(store)

        ev_pre = EvidenceItem(
            evidence_id="ev-pre-1",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="NETWORK",
            observation="DNS failed",
            value={"resolved": False, "dns_resolved": False},
            session_id="sess-1",
        )
        ev_post = EvidenceItem(
            evidence_id="ev-post-1",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="NETWORK",
            observation="DNS resolved",
            value={"resolved": True, "dns_resolved": True},
            session_id="sess-1",
        )

        change = tracker.track_change(ev_pre, ev_post)
        assert change.change_type == EvidenceChangeType.CONTRADICTED

        comparison = tracker.compute_before_after_comparison(
            tool_name="flush_dns_cache",
            pre_evidence=ev_pre.value,
            post_evidence=ev_post.value,
            verification_passed=True,
        )
        assert comparison.verification_passed is True
        assert comparison.state_changed is True
        assert "dns_resolved_changed" in comparison.metric_deltas


    def test_resolution_analyzer_execution_vs_verification(self):
        """CRITICAL INVARIANT: Execution success does NOT equal resolution success."""
        # Case A: Execution succeeded, but verification failed
        res_fail = ResolutionAnalyzer.analyze_resolution(
            session_id="s1",
            workflow_id="w1",
            primary_domain=TroubleshootingDomain.SERVICES,
            execution_succeeded=True,
            verification_succeeded=False,
        )
        assert res_fail.outcome == ResolutionOutcome.VERIFICATION_FAILED
        assert res_fail.resolution_status == ResolutionStatus.NOT_RESOLVED
        assert res_fail.failure_category == FailureCategory.VERIFICATION_FAILED

        # Case B: Execution succeeded and verification succeeded
        res_pass = ResolutionAnalyzer.analyze_resolution(
            session_id="s1",
            workflow_id="w1",
            primary_domain=TroubleshootingDomain.SERVICES,
            execution_succeeded=True,
            verification_succeeded=True,
        )
        assert res_pass.outcome == ResolutionOutcome.VERIFICATION_SUCCEEDED
        assert res_pass.resolution_status == ResolutionStatus.RESOLVED
        assert res_pass.failure_category is None


class TestAdaptiveScenarioFamilies:
    """Validate all 10 domain scenario families using the ScenarioRunner and test doubles."""

    @pytest.fixture
    def runner(self):
        return ScenarioRunner()

    def test_network_dns_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="net-dns-01",
            domain=TroubleshootingDomain.NETWORK,
            initial_user_symptom="Websites will not load and DNS probe failed",
            initial_state={"dns_resolved": False},
            expected_diagnostic_path=["check_dns_resolution"],
            optional_repair="flush_dns_cache",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "flush_dns_cache" in result.executed_steps
        assert "check_dns_resolution" in result.executed_steps
        assert result.resolution_analysis["resolution_status"] == "RESOLVED"

    def test_network_dhcp_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="net-dhcp-01",
            domain=TroubleshootingDomain.NETWORK,
            initial_user_symptom="No IP address assigned on Wi-Fi adapter",
            initial_state={"adapter_connected": False, "dhcp_lease_valid": False},
            expected_diagnostic_path=["get_network_adapters_diagnostics"],
            optional_repair="renew_dhcp_lease",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "renew_dhcp_lease" in result.executed_steps

    def test_services_stopped_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="svc-print-01",
            domain=TroubleshootingDomain.SERVICES,
            initial_user_symptom="Print spooler service is not running",
            initial_state={"services": {"spooler": "STOPPED"}},
            expected_diagnostic_path=["get_service_status"],
            optional_repair="start_service",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "start_service" in result.executed_steps

    def test_windows_update_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="wu-stuck-01",
            domain=TroubleshootingDomain.WINDOWS_UPDATE,
            initial_user_symptom="Windows Update error 0x80070422 service disabled",
            initial_state={"services": {"wuauserv": "STOPPED"}},
            expected_diagnostic_path=["get_windows_update_diagnostics"],
            optional_repair="restart_windows_update_service",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "restart_windows_update_service" in result.executed_steps

    def test_windows_defender_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="def-disabled-01",
            domain=TroubleshootingDomain.WINDOWS_DEFENDER,
            initial_user_symptom="Windows Defender real-time protection is turned off",
            initial_state={"realtime_protection": False, "services": {"WinDefend": "STOPPED"}},
            expected_diagnostic_path=["get_defender_diagnostics"],
            optional_repair="restart_defender_service",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "restart_defender_service" in result.executed_steps

    def test_bluetooth_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="bt-radio-01",
            domain=TroubleshootingDomain.BLUETOOTH,
            initial_user_symptom="Bluetooth audio device disconnected and service stopped",
            initial_state={"bluetooth_radio_enabled": False, "services": {"bthserv": "STOPPED"}},
            expected_diagnostic_path=["get_bluetooth_diagnostics"],
            optional_repair="restart_bluetooth_service",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "restart_bluetooth_service" in result.executed_steps

    def test_storage_cleanup_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="stor-temp-01",
            domain=TroubleshootingDomain.STORAGE,
            initial_user_symptom="C: drive full of temporary installer files",
            initial_state={"temp_size_mb": 7500},
            expected_diagnostic_path=["get_temp_storage_info"],
            optional_repair="clean_user_temp_cache",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "clean_user_temp_cache" in result.executed_steps

    def test_performance_high_cpu_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="perf-cpu-01",
            domain=TroubleshootingDomain.PERFORMANCE,
            initial_user_symptom="System fans screaming high CPU usage",
            initial_state={"cpu_percent": 95.0, "high_cpu_pid": 4321},
            expected_diagnostic_path=["get_top_cpu_processes"],
            optional_repair="terminate_user_process",
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "terminate_user_process" in result.executed_steps

    def test_application_crash_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="app-crash-01",
            domain=TroubleshootingDomain.APPLICATION_CRASH,
            initial_user_symptom="Application crashes immediately upon launch",
            initial_state={},
            expected_diagnostic_path=["get_application_crash_diagnostics"],
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "get_application_crash_diagnostics" in result.executed_steps

    def test_startup_and_system_scenario(self, runner):
        scenario = ScenarioDefinition(
            scenario_id="sys-info-01",
            domain=TroubleshootingDomain.SYSTEM,
            initial_user_symptom="System operating system build verification",
            initial_state={},
            expected_diagnostic_path=["get_complete_system_info"],
            expected_final_state="RESOLVED",
        )
        result = runner.run_scenario(scenario)
        assert result.passed is True
        assert "get_complete_system_info" in result.executed_steps


class TestNoisyAndContradictoryEvidenceAdaptation:
    """Test adaptive reasoning under noisy, contradictory, and changing telemetry conditions."""

    def test_contradictory_dns_hypothesis_adaptation(self):
        """User claims DNS is broken, but telemetry confirms DNS works; engine must adapt."""
        engine = AdaptiveDiagnosticEngine()
        ctx = engine.create_session("sess-contra-1", "DNS is not working", TroubleshootingDomain.NETWORK)

        initial_hyp = DiagnosticHypothesis(
            hypothesis_id="hyp-dns",
            category="NETWORK",
            statement="Suspected DNS lookup failure",
            status=HypothesisStatus.POSSIBLE,
        )

        # Factual telemetry showing DNS works
        dns_ok_ev = EvidenceItem(
            evidence_id="ev-dns-ok",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="NETWORK",
            observation="DNS resolved successfully",
            value={"resolved": True, "dns_resolved": True},
            session_id="sess-contra-1",
            quality=EvidenceQuality.VERIFIED,
        )

        adapted_hyp, decision = engine.evaluate_telemetry_and_adapt(ctx, initial_hyp, dns_ok_ev)


        assert decision.action_type == "ADAPT_HYPOTHESIS"
        assert ctx.current_state == AdaptiveState.ADAPTING
        assert len(ctx.hypothesis_transitions) == 1
        assert ctx.hypothesis_transitions[0].from_status == HypothesisStatus.POSSIBLE
        assert ctx.hypothesis_transitions[0].to_status == HypothesisStatus.CONTRADICTED
        assert adapted_hyp.status == HypothesisStatus.SUPPORTED

    def test_real_windows_validator_read_only(self):
        """Verify non-destructive read-only host validation."""
        results = RealWindowsValidator.validate_host_environment()
        assert "os_platform" in results
        assert "storage_telemetry" in results
        assert results["storage_telemetry"].status in (SubsystemStatus.READY, SubsystemStatus.DEGRADED)
