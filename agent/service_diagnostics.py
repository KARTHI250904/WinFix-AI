"""Windows Services Diagnostics Orchestrator for WinFix AI (Phase 10).

Coordinates evidence collection across approved read-only service diagnostic tools,
evaluates service states, startup configurations, and maps user troubleshooting scenarios
to deterministic, evidence-backed diagnostic findings.

Strictly read-only: NO service state changes are performed in this module.
"""

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Dict, List, Optional

from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import DiagnosticRepository, SessionRepository

logger = logging.getLogger(__name__)

# Keyword to service mapping for intelligent scenario deduction
KEYWORD_SERVICE_MAP = {
    "printer": "Spooler",
    "print": "Spooler",
    "spooler": "Spooler",
    "printing": "Spooler",
    "update": "wuauserv",
    "windows update": "wuauserv",
    "bluetooth": "bthserv",
    "defender": "WinDefend",
    "antivirus": "WinDefend",
    "firewall": "mpssvc",
    "time": "W32Time",
    "clock": "W32Time",
    "network": "Dhcp",
    "dhcp": "Dhcp",
    "dns": "Dnscache",
    "bits": "bits",
    "transfer": "bits",
}


@dataclass
class ServiceDiagnosis:
    """Structured, evidence-based service diagnosis result."""

    problem_category: str
    summary: str
    target_service: Optional[str] = None
    observed_evidence: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)
    confidence: float = 0.8
    recommended_next_steps: List[str] = field(default_factory=list)
    repair_available: bool = False
    proposed_tool: Optional[str] = None
    proposed_args: Optional[Dict[str, Any]] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize diagnosis result to dictionary."""
        return {
            "problem_category": self.problem_category,
            "summary": self.summary,
            "target_service": self.target_service,
            "observed_evidence": self.observed_evidence,
            "interpretation": self.interpretation,
            "confidence": self.confidence,
            "recommended_next_steps": self.recommended_next_steps,
            "repair_available": self.repair_available,
            "proposed_tool": self.proposed_tool,
            "proposed_args": self.proposed_args,
            "tool_results": self.tool_results,
        }


class ServiceDiagnosticsOrchestrator:
    """Coordinates read-only Windows service diagnostics and scenario analysis."""

    def __init__(
        self,
        safety_engine: Optional[SafetyEngine] = None,
        registry: Optional[ToolRegistry] = None,
        llm_client: Optional[OllamaClient] = None,
        db_mgr: Optional[DatabaseManager] = None,
    ) -> None:
        self.safety_engine = safety_engine or default_safety_engine
        self.registry = registry or default_tool_registry
        self.llm = llm_client or ollama_client
        self.db_manager = db_mgr or default_db_manager
        self.session_repo = SessionRepository(self.db_manager)
        self.diagnostic_repo = DiagnosticRepository(self.db_manager)

    def _infer_target_service_from_text(self, text: Optional[str]) -> Optional[str]:
        """Attempt to extract or infer a Windows service name from user description."""
        if not text:
            return None
        lower_text = text.lower()
        for kw, svc in KEYWORD_SERVICE_MAP.items():
            # Check whole word match
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, lower_text):
                return svc
        return None

    def diagnose_service(
        self,
        service_name: str,
        session_id: Optional[str] = None,
    ) -> ServiceDiagnosis:
        """Inspect a specific Windows service and evaluate operational state."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []

        # Execute get_service_details
        details_res = self.safety_engine.execute(
            tool_name="get_service_details",
            arguments={"service_name": service_name},
            session_id=session_id,
        )
        tool_results.append(details_res)

        if not details_res["success"]:
            err = details_res.get("error", {})
            msg = err.get("message", "Service query failed.")
            return ServiceDiagnosis(
                problem_category="service_not_found",
                summary=f"Unable to inspect service '{service_name}': {msg}",
                target_service=service_name,
                observed_evidence=[f"Query for service '{service_name}' failed with code: {err.get('code', 'ERROR')}"],
                interpretation=[f"The requested service identifier '{service_name}' could not be located or queried."],
                confidence=0.9,
                recommended_next_steps=["Verify the exact service name in Windows Services (services.msc)."],
                repair_available=False,
                tool_results=tool_results,
            )

        data = details_res.get("data", {})
        s_name = data.get("name", service_name)
        disp_name = data.get("display_name", s_name)
        status = data.get("status", "UNKNOWN")
        start_type = data.get("start_type", "UNKNOWN")
        desc = data.get("description", "")

        observed_evidence.append(f"Service '{s_name}' ({disp_name}) status is {status}.")
        observed_evidence.append(f"Startup configuration type is {start_type}.")
        if desc:
            observed_evidence.append(f"Description: {desc[:120]}...")

        # Scenario B: Service Disabled
        if start_type == "DISABLED":
            interpretation.append(f"Service '{disp_name}' is set to DISABLED in Windows configuration.")
            interpretation.append("WinFix AI does not automatically alter startup types in Phase 10.")
            recommended_next_steps.append(
                f"If '{disp_name}' is required, open Windows Services (services.msc) and adjust startup type to Automatic/Manual."
            )
            return ServiceDiagnosis(
                problem_category="service_disabled",
                summary=f"Service '{disp_name}' is currently DISABLED.",
                target_service=s_name,
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.95,
                recommended_next_steps=recommended_next_steps,
                repair_available=False,
                tool_results=tool_results,
            )

        # Scenario A: Service Stopped
        if status == "STOPPED":
            interpretation.append(f"Service '{disp_name}' is currently STOPPED.")
            interpretation.append(f"Starting '{disp_name}' may resolve related subsystem issues.")
            recommended_next_steps.append(f"Propose starting service '{s_name}' via controlled start_service tool.")
            return ServiceDiagnosis(
                problem_category="service_stopped",
                summary=f"Service '{disp_name}' is currently stopped.",
                target_service=s_name,
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.9,
                recommended_next_steps=recommended_next_steps,
                repair_available=True,
                proposed_tool="start_service",
                proposed_args={"service_name": s_name},
                tool_results=tool_results,
            )

        # Scenario C: Service Running
        if status == "RUNNING":
            interpretation.append(f"Service '{disp_name}' is active and RUNNING normally.")
            interpretation.append("No automatic restart is recommended without explicit failure evidence.")
            recommended_next_steps.append("Service is healthy. Investigate client logs or dependencies if issues persist.")
            return ServiceDiagnosis(
                problem_category="service_running",
                summary=f"Service '{disp_name}' is running normally.",
                target_service=s_name,
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.85,
                recommended_next_steps=recommended_next_steps,
                repair_available=False,
                tool_results=tool_results,
            )

        # Scenario D: Pending or Paused states
        interpretation.append(f"Service '{disp_name}' is in transitional or paused state: {status}.")
        recommended_next_steps.append("Allow time for state transition to complete, or inspect event logs.")
        return ServiceDiagnosis(
            problem_category="service_transitional",
            summary=f"Service '{disp_name}' is in {status} state.",
            target_service=s_name,
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.75,
            recommended_next_steps=recommended_next_steps,
            repair_available=False,
            tool_results=tool_results,
        )

    def run_diagnostics(
        self,
        session_id: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> ServiceDiagnosis:
        """Execute general or targeted service diagnostics and synthesize findings."""
        target_svc = self._infer_target_service_from_text(user_prompt)

        # If user problem explicitly mentions or maps to a specific service, diagnose it directly
        if target_svc:
            return self.diagnose_service(target_svc, session_id=session_id)

        # Otherwise perform general monitored common services scan
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []

        common_res = self.safety_engine.execute(
            tool_name="list_common_services",
            session_id=session_id,
        )
        tool_results.append(common_res)

        stopped_actionable: List[Dict[str, Any]] = []
        if common_res["success"] and common_res.get("data"):
            data = common_res["data"]
            svcs = data.get("services", [])
            total_monitored = data.get("total_monitored", len(svcs))
            running_count = data.get("running_count", 0)

            observed_evidence.append(f"Monitored common services: {running_count}/{total_monitored} active.")

            for s in svcs:
                if not s.get("is_running") and s.get("status") == "STOPPED":
                    if s.get("start_type") != "DISABLED":
                        stopped_actionable.append(s)

        if stopped_actionable:
            first_stopped = stopped_actionable[0]
            s_name = first_stopped.get("name", "")
            d_name = first_stopped.get("display_name", s_name)

            observed_evidence.append(f"Detected stopped monitored service: {d_name} ({s_name}).")
            interpretation.append(f"Key service '{d_name}' is stopped but configured to run on demand/auto.")
            recommended_next_steps.append(f"Start service '{d_name}' to restore full operational capability.")

            return ServiceDiagnosis(
                problem_category="service_stopped",
                summary=f"Detected stopped background service: {d_name}.",
                target_service=s_name,
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.85,
                recommended_next_steps=recommended_next_steps,
                repair_available=True,
                proposed_tool="start_service",
                proposed_args={"service_name": s_name},
                tool_results=tool_results,
            )

        # All healthy
        observed_evidence.append("All primary system troubleshooting services are operational.")
        interpretation.append("No common Windows service failure detected.")
        recommended_next_steps.append("Check specific service inventory if a custom background worker failed.")

        return ServiceDiagnosis(
            problem_category="general_services",
            summary="All core Windows troubleshooting services are running normally.",
            target_service=None,
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.9,
            recommended_next_steps=recommended_next_steps,
            repair_available=False,
            tool_results=tool_results,
        )
