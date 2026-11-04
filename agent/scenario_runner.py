"""WinFix AI — Scenario Runner & Deterministic Simulation Doubles (Phase 30).

Provides non-destructive test doubles for Windows subsystems and an automated scenario runner
for validating adaptive troubleshooting workflows across all 11 domains and noisy/contradictory telemetry.
Strictly adheres to:
  Simulation != Destructive OS Mutation
  AST 0 prohibited calls
  Fail-Closed Invariants
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from agent.adaptive_engine import AdaptiveDiagnosticEngine
from agent.adaptive_models import (
    AdaptiveSessionContext,
    AdaptiveState,
    BeforeAfterComparison,
    DiagnosticDecision,
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
from agent.resolution_analyzer import ResolutionAnalyzer

from agent.scenario_models import ScenarioDefinition, ScenarioExecutionResult
from agent.verification_registry import VerificationRegistry
from agent.workflow_models import ResolutionStatus


logger = logging.getLogger("winfix.SCENARIO_RUNNER")


class FakeWindowsEnvironment:
    """Deterministic, in-memory state doubles simulating Windows subsystems safely."""

    def __init__(self, initial_state: Optional[Dict[str, Any]] = None) -> None:
        self.state: Dict[str, Any] = initial_state or {}
        # Services state (e.g., {"wuauserv": "STOPPED", "bthserv": "RUNNING"})
        self.services: Dict[str, str] = self.state.get("services", {
            "wuauserv": "STOPPED",
            "bthserv": "STOPPED",
            "WinDefend": "RUNNING",
            "spooler": "STOPPED",
        })
        # Network state
        self.dns_resolved: bool = self.state.get("dns_resolved", False)
        self.adapter_connected: bool = self.state.get("adapter_connected", True)
        self.dhcp_lease_valid: bool = self.state.get("dhcp_lease_valid", True)
        # Storage state
        self.temp_size_mb: int = self.state.get("temp_size_mb", 6500)
        self.free_disk_gb: int = self.state.get("free_disk_gb", 15)
        # Performance state
        self.cpu_percent: float = self.state.get("cpu_percent", 92.0)
        self.high_cpu_pid: int = self.state.get("high_cpu_pid", 1234)
        # Defender state
        self.realtime_protection: bool = self.state.get("realtime_protection", False)
        self.antivirus_enabled: bool = self.state.get("antivirus_enabled", True)
        # Bluetooth state
        self.bluetooth_radio_enabled: bool = self.state.get("bluetooth_radio_enabled", False)

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Simulate execution of safe diagnostic or medium repair tools deterministically."""
        args = arguments or {}

        # 1. DNS Tools
        if tool_name == "check_dns_resolution":
            return {"success": True, "resolved": self.dns_resolved, "dns_resolved": self.dns_resolved, "server": "1.1.1.1"}
        if tool_name == "flush_dns_cache":
            self.dns_resolved = True  # Simulated repair effect
            return {"success": True, "output": "Successfully flushed the DNS Resolver Cache."}

        # 2. Network & DHCP Tools
        if tool_name == "get_network_adapters_diagnostics":
            return {"success": True, "connected": self.adapter_connected, "dhcp_lease": self.dhcp_lease_valid}
        if tool_name == "check_internet_connectivity":
            is_ok = self.adapter_connected and self.dhcp_lease_valid
            return {"success": True, "internet_connected": is_ok, "status": "ok" if is_ok else "failed"}
        if tool_name == "renew_dhcp_lease":
            self.dhcp_lease_valid = True
            self.adapter_connected = True
            return {"success": True, "output": "DHCP lease renewed."}


        # 3. Service Tools
        if tool_name in ("get_service_status", "get_services_diagnostics"):
            svc = args.get("service_name", "wuauserv")
            status = self.services.get(svc, "STOPPED")
            return {"success": True, "service_name": svc, "status": status, "state": status}
        if tool_name in ("start_service", "restart_service"):
            svc = args.get("service_name", "wuauserv")
            self.services[svc] = "RUNNING"
            return {"success": True, "service_name": svc, "status": "RUNNING"}
        if tool_name == "stop_service":
            svc = args.get("service_name", "wuauserv")
            self.services[svc] = "STOPPED"
            return {"success": True, "service_name": svc, "status": "STOPPED"}

        # 4. Windows Update Tools
        if tool_name == "get_windows_update_diagnostics":
            status = self.services.get("wuauserv", "STOPPED")
            return {"success": True, "service_status": status, "status": status}
        if tool_name == "restart_windows_update_service":
            self.services["wuauserv"] = "RUNNING"
            return {"success": True, "status": "RUNNING", "output": "Windows Update service restarted."}

        # 5. Defender Tools
        if tool_name == "get_defender_diagnostics":
            return {
                "success": True,
                "realtime_protection": self.realtime_protection,
                "antivirus_enabled": self.antivirus_enabled,
                "status": "RUNNING" if self.realtime_protection else "DEGRADED",
            }
        if tool_name == "restart_defender_service":
            self.realtime_protection = True
            self.services["WinDefend"] = "RUNNING"
            return {"success": True, "output": "Defender service restarted."}

        # 6. Bluetooth Tools
        if tool_name == "get_bluetooth_diagnostics":
            status = self.services.get("bthserv", "STOPPED")
            return {"success": True, "service_status": status, "radio_enabled": self.bluetooth_radio_enabled}
        if tool_name == "restart_bluetooth_service":
            self.services["bthserv"] = "RUNNING"
            self.bluetooth_radio_enabled = True
            return {"success": True, "output": "Bluetooth service restarted."}

        # 7. Storage Tools
        if tool_name == "get_temp_storage_info":
            return {"success": True, "total_size_mb": self.temp_size_mb, "size_mb": self.temp_size_mb}
        if tool_name == "clean_user_temp_cache":
            self.temp_size_mb = 120  # Cleaned state
            return {"success": True, "cleaned_mb": 6380, "output": "Temp cache cleared."}
        if tool_name == "get_storage_diagnostics":
            return {"success": True, "free_gb": self.free_disk_gb}

        # 8. Performance Tools
        if tool_name in ("get_top_cpu_processes", "get_resource_snapshot"):
            return {"success": True, "cpu_percent": self.cpu_percent, "top_process_pid": self.high_cpu_pid}
        if tool_name == "terminate_user_process":
            self.cpu_percent = 15.0  # Normalized load
            return {"success": True, "terminated_pid": self.high_cpu_pid}

        # 9. Application Crash Tools
        if tool_name == "get_application_crash_diagnostics":
            return {"success": True, "recent_crashes_found": True, "faulting_module": "example.dll"}

        # 10. System Tools
        if tool_name == "get_complete_system_info":
            return {"success": True, "os": "Windows 11 Pro", "build": "22631"}

        # Fallback default
        return {"success": True, "message": f"Tool '{tool_name}' executed in test double."}


class ScenarioRunner:
    """Executes scenario definitions against test doubles and adaptive diagnostic engine."""

    def __init__(self) -> None:
        self.evidence_store = EvidenceStore()
        self.engine = AdaptiveDiagnosticEngine(evidence_store=self.evidence_store)
        self.verification_reg = VerificationRegistry()

    def run_scenario(self, scenario: ScenarioDefinition) -> ScenarioExecutionResult:
        """Run an automated end-to-end adaptive scenario."""
        session_id = f"scenario-{scenario.scenario_id}-{uuid.uuid4().hex[:6]}"
        env = FakeWindowsEnvironment(initial_state=dict(scenario.initial_state))
        ctx = self.engine.create_session(session_id, scenario.initial_user_symptom, scenario.domain)

        executed_steps: List[str] = []
        failure_reasons: List[str] = []
        current_hyp: Optional[DiagnosticHypothesis] = None
        before_after: Optional[BeforeAfterComparison] = None
        pre_evidence_dict: Dict[str, Any] = {}

        # 1. Execute initial diagnostic sequence or inject available evidence
        for diag_tool in scenario.expected_diagnostic_path:
            if not ctx.can_execute_step():
                failure_reasons.append("Step budget exceeded during diagnostic sequence.")
                break

            executed_steps.append(diag_tool)
            ctx.record_step(diag_tool, is_safe=True)
            res = env.execute_tool(diag_tool)

            ev = EvidenceItem(
                evidence_id=f"ev-{len(executed_steps)}",
                evidence_type=EvidenceType.SYSTEM,
                source=EvidenceSource.WINDOWS_TOOL,
                category=scenario.domain.value if isinstance(scenario.domain, TroubleshootingDomain) else str(scenario.domain),
                observation=f"Diagnostic result from {diag_tool}",
                value=res,
                session_id=session_id,
                quality=EvidenceQuality.VERIFIED,
            )
            pre_evidence_dict = res
            current_hyp, decision = self.engine.evaluate_telemetry_and_adapt(ctx, current_hyp, ev)

        # 2. Inject noisy/contradictory evidence if specified
        for contra in scenario.contradictory_evidence:
            ev_contra = EvidenceItem(
                evidence_id=f"ev-contra-{uuid.uuid4().hex[:6]}",
                evidence_type=EvidenceType.SYSTEM,
                source=EvidenceSource.WINDOWS_TOOL,
                category=scenario.domain.value if isinstance(scenario.domain, TroubleshootingDomain) else str(scenario.domain),
                observation="Noisy telemetry observation",
                value=contra,
                session_id=session_id,
                quality=EvidenceQuality.VERIFIED,
            )
            current_hyp, decision = self.engine.evaluate_telemetry_and_adapt(ctx, current_hyp, ev_contra)


        # 3. Propose and execute repair if specified
        if scenario.optional_repair:
            repair_tool = scenario.optional_repair
            executed_steps.append(repair_tool)
            ctx.record_step(repair_tool, is_safe=False)
            repair_res = env.execute_tool(repair_tool)
            exec_succeeded = repair_res.get("success", False)

            # 4. Verification step
            verif_rule = self.verification_reg.get_rule_for_tool(repair_tool)
            if verif_rule:
                verif_tool = verif_rule.verification_tool
                executed_steps.append(verif_tool)
                ctx.record_step(verif_tool, is_safe=True)
                post_res = env.execute_tool(verif_tool)

                res_status, explanation_str = self.verification_reg.evaluate_verification(
                    repair_tool=repair_tool,
                    before_state=pre_evidence_dict,
                    after_state=post_res,
                )
                verif_succeeded = (res_status == ResolutionStatus.RESOLVED)

                # Compute before/after
                evolution = EvidenceEvolutionTracker(self.evidence_store)
                before_after = evolution.compute_before_after_comparison(
                    tool_name=repair_tool,
                    pre_evidence=pre_evidence_dict,
                    post_evidence=post_res,
                    verification_passed=verif_succeeded,
                    details=explanation_str,
                )
            else:
                verif_succeeded = exec_succeeded

        else:
            # Diagnostic-only scenario completed
            exec_succeeded = True
            verif_succeeded = True

        # 5. Analyze resolution
        res_analysis = ResolutionAnalyzer.analyze_resolution(
            session_id=session_id,
            workflow_id=ctx.workflow_id,
            primary_domain=ctx.primary_domain,
            execution_succeeded=exec_succeeded,
            verification_succeeded=verif_succeeded,
            before_after=before_after,
            has_contradictions=len(scenario.contradictory_evidence) > 0 and not verif_succeeded,
        )


        final_state = res_analysis.resolution_status.value
        passed = (final_state == scenario.expected_final_state) or (
            scenario.expected_final_state == "UNRESOLVED" and final_state in ("NOT_RESOLVED", "UNRESOLVED")
        )

        return ScenarioExecutionResult(
            scenario_id=scenario.scenario_id,
            passed=passed,
            domain=scenario.domain,
            executed_steps=executed_steps,
            hypothesis_transitions=[t.to_dict() for t in ctx.hypothesis_transitions],
            final_state=final_state,
            resolution_analysis=res_analysis.to_dict(),
            failure_reasons=failure_reasons,
        )
