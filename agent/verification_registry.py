"""WinFix AI — Verification Registry & Deterministic Evaluation Rules (Phase 29).

Authoritative registry of post-repair deterministic verification rules.
Maps each allowlisted repair tool to its corresponding verification tool and evaluation logic.
Strictly adheres to:
  LLM cannot define or override verification logic
  Repair Execution != Resolution
  Verification evaluates factual before vs after state
"""

from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from agent.workflow_models import ResolutionStatus

logger = logging.getLogger("winfix.VERIFICATION_REGISTRY")


@dataclass(frozen=True)
class VerificationRule:
    """Deterministic rule governing post-repair verification."""

    verification_id: str
    repair_tool: str
    expected_state: str
    verification_tool: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary."""
        return {
            "verification_id": self.verification_id,
            "repair_tool": self.repair_tool,
            "expected_state": self.expected_state,
            "verification_tool": self.verification_tool,
            "description": self.description,
        }


class VerificationRegistry:
    """Authoritative registry for post-repair deterministic verification rules."""

    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None:
        self.tool_registry = tool_registry or default_tool_registry
        self._rules: Dict[str, VerificationRule] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Register deterministic verification rules for all MEDIUM repair tools."""
        rules = [
            VerificationRule(
                verification_id="vrule_dns",
                repair_tool="flush_dns_cache",
                expected_state="dns_resolved == True",
                verification_tool="check_dns_resolution",
                description="Verifies DNS hostname resolution succeeds after cache flush.",
            ),
            VerificationRule(
                verification_id="vrule_dhcp",
                repair_tool="renew_dhcp_lease",
                expected_state="internet_connected == True",
                verification_tool="check_internet_connectivity",
                description="Verifies internet connectivity responds after DHCP renewal.",
            ),
            VerificationRule(
                verification_id="vrule_service",
                repair_tool="restart_service",
                expected_state="state == Running",
                verification_tool="get_service_status",
                description="Verifies target Windows service reports Running state after restart.",
            ),
            VerificationRule(
                verification_id="vrule_service_start",
                repair_tool="start_service",
                expected_state="state == Running",
                verification_tool="get_service_status",
                description="Verifies target Windows service reports Running state after start.",
            ),
            VerificationRule(
                verification_id="vrule_service_stop",
                repair_tool="stop_service",
                expected_state="state == Stopped",
                verification_tool="get_service_status",
                description="Verifies target Windows service reports Stopped state after stop.",
            ),
            VerificationRule(
                verification_id="vrule_temp_cleanup",
                repair_tool="clean_user_temp_cache",
                expected_state="disk_status == ok",
                verification_tool="get_storage_diagnostics",
                description="Verifies volume storage status and free space after temp cleanup.",
            ),
            VerificationRule(
                verification_id="vrule_win_update",
                repair_tool="restart_windows_update_service",
                expected_state="wuauserv_running == True",
                verification_tool="get_windows_update_diagnostics",
                description="Verifies Windows Update service is healthy and running after restart.",
            ),
            VerificationRule(
                verification_id="vrule_defender",
                repair_tool="restart_defender_service",
                expected_state="defender_running == True",
                verification_tool="get_defender_diagnostics",
                description="Verifies Defender service is active and running after restart.",
            ),
            VerificationRule(
                verification_id="vrule_bluetooth",
                repair_tool="restart_bluetooth_service",
                expected_state="bthserv_running == True",
                verification_tool="get_bluetooth_diagnostics",
                description="Verifies Bluetooth Support Service (bthserv) is active after restart.",
            ),
            VerificationRule(
                verification_id="vrule_process_terminate",
                repair_tool="terminate_user_process",
                expected_state="process_terminated == True",
                verification_tool="get_top_cpu_processes",
                description="Verifies target user process is no longer running after termination.",
            ),
        ]

        for r in rules:
            self.register(r)

    def register(self, rule: VerificationRule) -> None:
        """Register a verification rule after validating tool existence."""
        repair_def = self.tool_registry.get(rule.repair_tool)
        verif_def = self.tool_registry.get(rule.verification_tool)

        if not repair_def:
            logger.warning(f"Repair tool '{rule.repair_tool}' not found in ToolRegistry")
            return
        if not verif_def or verif_def.risk != RiskLevel.SAFE:
            logger.warning(f"Verification tool '{rule.verification_tool}' must be registered and SAFE")
            return

        self._rules[rule.repair_tool] = rule

    def get_rule_for_tool(self, repair_tool: str) -> Optional[VerificationRule]:
        """Look up the verification rule for a specific repair tool."""
        return self._rules.get(repair_tool)

    def list_rules(self) -> List[VerificationRule]:
        """List all registered verification rules."""
        return list(self._rules.values())

    def evaluate_verification(
        self,
        repair_tool: str,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
    ) -> Tuple[ResolutionStatus, str]:
        """Deterministically evaluate before vs after verification state according to registered rule."""
        rule = self.get_rule_for_tool(repair_tool)
        if not rule:
            return ResolutionStatus.INCONCLUSIVE, f"No verification rule registered for repair tool '{repair_tool}'"

        if not before_state or not after_state:
            return ResolutionStatus.INCONCLUSIVE, "Missing before or after verification state data"

        # Domain-specific deterministic evaluation
        if repair_tool == "flush_dns_cache":
            before_dns = before_state.get("dns_resolved", False)
            after_dns = after_state.get("dns_resolved", False)
            if not before_dns and after_dns:
                return ResolutionStatus.RESOLVED, "DNS resolution restored successfully following cache flush"
            if not before_dns and not after_dns:
                return ResolutionStatus.NOT_RESOLVED, "DNS resolution continues to fail after cache flush"

        elif repair_tool in ["restart_service", "start_service"]:
            before_svc = str(before_state.get("state", "")).lower()
            after_svc = str(after_state.get("state", "")).lower()
            if before_svc != "running" and after_svc == "running":
                return ResolutionStatus.RESOLVED, "Service successfully restored to Running state"
            if after_svc != "running":
                return ResolutionStatus.NOT_RESOLVED, f"Service remains in non-running state: {after_svc}"

        elif repair_tool == "stop_service":
            after_svc = str(after_state.get("state", "")).lower()
            if after_svc == "stopped":
                return ResolutionStatus.RESOLVED, "Service successfully stopped"
            else:
                return ResolutionStatus.NOT_RESOLVED, f"Service remains in non-stopped state: {after_svc}"

        elif repair_tool == "renew_dhcp_lease":
            before_ok = before_state.get("internet_connected", False) or before_state.get("status") == "ok"
            after_ok = after_state.get("internet_connected", False) or after_state.get("status") == "ok"
            if not before_ok and after_ok:
                return ResolutionStatus.RESOLVED, "Connectivity restored after DHCP lease renewal"
            if not after_ok:
                return ResolutionStatus.NOT_RESOLVED, "Connectivity failing after DHCP lease renewal"

        # Fallback to general health status check
        before_ok = before_state.get("status") in ["ok", "healthy", "success"] or before_state.get("success") is True
        after_ok = after_state.get("status") in ["ok", "healthy", "success"] or after_state.get("success") is True

        if not before_ok and after_ok:
            return ResolutionStatus.RESOLVED, f"Verification rule '{rule.verification_id}' confirmed issue resolution"
        elif not after_ok:
            return ResolutionStatus.NOT_RESOLVED, f"Verification rule '{rule.verification_id}' indicates issue persists"
        else:
            return ResolutionStatus.RESOLVED, f"Verification rule '{rule.verification_id}' confirmed healthy state"


default_verification_registry = VerificationRegistry()
