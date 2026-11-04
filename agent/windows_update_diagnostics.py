"""Windows Update Diagnostics Orchestrator for WinFix AI (Phase 12).

Coordinates evidence collection across approved read-only Windows Update diagnostic tools,
evaluates wuauserv state, dependency services readiness, update history, and recent failure logs.

Strictly read-only: NO update installation, component deletion, or state modification.
"""

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Dict, List, Optional

from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import DiagnosticRepository, SessionRepository

logger = logging.getLogger(__name__)

WINDOWS_UPDATE_CATEGORIES = {
    "service_stopped",
    "service_disabled",
    "dependency_issue",
    "update_errors",
    "configuration_issue",
    "general_update",
    "healthy",
}


@dataclass
class WindowsUpdateDiagnosis:
    """Structured, evidence-based Windows Update diagnosis result."""

    problem_category: str
    summary: str
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
            "observed_evidence": self.observed_evidence,
            "interpretation": self.interpretation,
            "confidence": self.confidence,
            "recommended_next_steps": self.recommended_next_steps,
            "repair_available": self.repair_available,
            "proposed_tool": self.proposed_tool,
            "proposed_args": self.proposed_args,
            "tool_results": self.tool_results,
        }


class WindowsUpdateDiagnosticsOrchestrator:
    """Coordinates read-only Windows Update diagnostics and scenario analysis."""

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

    def run_diagnostics(
        self,
        session_id: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> WindowsUpdateDiagnosis:
        """Execute read-only Windows Update diagnostic tools and synthesize findings."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []

        # 1. Execute unified aggregator
        diag_res = self.safety_engine.execute(
            tool_name="get_windows_update_diagnostics",
            session_id=session_id,
        )
        tool_results.append(diag_res)

        if not diag_res.get("success"):
            return WindowsUpdateDiagnosis(
                problem_category="general_update",
                summary="Failed to execute Windows Update diagnostics.",
                observed_evidence=["Diagnostic tool returned an error or is unsupported on this platform."],
                interpretation=["Unable to inspect Windows Update state reliably."],
                confidence=0.2,
                recommended_next_steps=["Check system permissions and verify Windows operating system."],
                repair_available=False,
                tool_results=tool_results,
            )

        diag_data = diag_res.get("data", {})
        service_data = diag_data.get("service_status") or {}
        dependencies_data = diag_data.get("dependencies") or {}
        config_data = diag_data.get("configuration") or {}
        history_data = diag_data.get("history") or {}
        errors_data = diag_data.get("errors") or {}
        health_data = diag_data.get("health") or {}

        # 2. Extract facts from service status
        wuauserv_status = service_data.get("status", "UNKNOWN")
        wuauserv_start = service_data.get("start_type", "UNKNOWN")
        wuauserv_running = service_data.get("is_running", False)

        observed_evidence.append(f"Windows Update service (wuauserv) status: {wuauserv_status} (Startup: {wuauserv_start}).")

        # 3. Extract facts from dependencies
        deps_healthy = dependencies_data.get("all_dependencies_healthy", True)
        degraded_deps = dependencies_data.get("degraded_services", [])
        if not deps_healthy and degraded_deps:
            observed_evidence.append(f"Degraded dependency service(s): {', '.join(degraded_deps)}.")
        else:
            observed_evidence.append("All core Windows Update dependency services are operational.")

        # 4. Extract facts from history & errors
        err_count = errors_data.get("count", 0)
        has_errors = errors_data.get("has_recent_errors", False)
        if has_errors:
            observed_evidence.append(f"Found {err_count} recent Windows Update error events in event logs.")

        history_count = history_data.get("count", 0)
        if history_count > 0:
            latest = history_data.get("latest_update", {})
            observed_evidence.append(f"Recorded {history_count} past updates. Latest: '{latest.get('title', 'Unknown')}' ({latest.get('result', 'Unknown')}).")

        # 5. Evaluate scenario classification
        problem_category = "healthy"
        repair_available = False
        proposed_tool = None
        proposed_args = None

        if wuauserv_status == "STOPPED":
            if wuauserv_start == "DISABLED":
                problem_category = "service_disabled"
                interpretation.append("The Windows Update service (wuauserv) is disabled and cannot start on demand.")
                recommended_next_steps.append("Open Services management (services.msc) and set Windows Update startup type to Manual or Automatic.")
            else:
                problem_category = "service_stopped"
                interpretation.append("The Windows Update service (wuauserv) is currently stopped.")
                recommended_next_steps.append("Restart the Windows Update service (wuauserv) to reinitialize update communications.")
                repair_available = True
                proposed_tool = "restart_windows_update_service"
                proposed_args = {}
        elif not deps_healthy and degraded_deps:
            problem_category = "dependency_issue"
            interpretation.append(f"Windows Update dependencies ({', '.join(degraded_deps)}) are stopped or degraded.")
            recommended_next_steps.append(f"Verify and resolve dependency service health for: {', '.join(degraded_deps)}.")
        elif has_errors:
            problem_category = "update_errors"
            interpretation.append(f"Windows Update has encountered {err_count} recent error events during downloads or installations.")
            recommended_next_steps.append("Restart the Windows Update service to clear transient error states, or check error codes in Windows Event Viewer.")
            repair_available = True
            proposed_tool = "restart_windows_update_service"
            proposed_args = {}
        else:
            problem_category = "healthy"
            interpretation.append("The Windows Update subsystem, services, and dependencies are healthy.")
            recommended_next_steps.append("No immediate repair actions required.")

        summary = (
            f"Windows Update Diagnosis ({problem_category}): {'; '.join(interpretation)}"
        )

        # 6. Record diagnostics in SQLite
        if session_id:
            try:
                self.diagnostic_repo.create_diagnostic_record(
                    session_id=session_id,
                    tool_name="get_windows_update_diagnostics",
                    category=problem_category,
                    raw_output=json.dumps(diag_data),
                    summary=summary,
                )
            except Exception as db_exc:
                logger.debug("Failed to record diagnostic in DB: %s", db_exc)

        return WindowsUpdateDiagnosis(
            problem_category=problem_category,
            summary=summary,
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.9,
            recommended_next_steps=recommended_next_steps,
            repair_available=repair_available,
            proposed_tool=proposed_tool,
            proposed_args=proposed_args,
            tool_results=tool_results,
        )
