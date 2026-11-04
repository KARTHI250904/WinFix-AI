"""Windows Defender Diagnostics Orchestrator for WinFix AI (Phase 13).

Coordinates evidence collection across approved read-only Windows Defender diagnostic tools,
evaluates WinDefend service state, real-time protection status, antivirus health, threat status,
and recent Defender event logs.

Strictly read-only: NO policy changes, exclusion tampering, real-time protection toggles, or disabling.
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

DEFENDER_CATEGORIES = {
    "service_stopped",
    "service_disabled",
    "realtime_disabled",
    "threats_detected",
    "antivirus_unhealthy",
    "recent_errors",
    "general_defender",
    "healthy",
}


@dataclass
class DefenderDiagnosis:
    """Structured, evidence-based Windows Defender diagnosis result."""

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


class DefenderDiagnosticsOrchestrator:
    """Coordinates read-only Windows Defender diagnostics and scenario analysis."""

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
    ) -> DefenderDiagnosis:
        """Execute read-only Windows Defender diagnostic tools and synthesize findings."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []

        # 1. Execute unified aggregator
        diag_res = self.safety_engine.execute(
            tool_name="get_defender_diagnostics",
            session_id=session_id,
        )
        tool_results.append(diag_res)

        if not diag_res.get("success"):
            return DefenderDiagnosis(
                problem_category="general_defender",
                summary="Failed to execute Windows Defender diagnostics.",
                observed_evidence=["Diagnostic tool returned an error or is unsupported on this platform."],
                interpretation=["Unable to inspect Windows Defender state reliably."],
                confidence=0.2,
                recommended_next_steps=["Check system permissions and verify Windows operating system."],
                repair_available=False,
                tool_results=tool_results,
            )

        diag_data = diag_res.get("data", {})
        service_data = diag_data.get("service_status") or {}
        realtime_data = diag_data.get("realtime_protection") or {}
        av_data = diag_data.get("antivirus_status") or {}
        threat_data = diag_data.get("threat_status") or {}
        health_data = diag_data.get("security_health") or {}
        events_data = diag_data.get("recent_events") or {}
        config_data = diag_data.get("configuration") or {}

        # 2. Extract facts from service status
        windefend_status = service_data.get("status", "UNKNOWN")
        windefend_start = service_data.get("start_type", "UNKNOWN")
        windefend_running = service_data.get("is_running", False)

        observed_evidence.append(f"Windows Defender service (WinDefend) status: {windefend_status} (Startup: {windefend_start}).")

        # 3. Extract facts from Real-Time Protection
        rt_enabled = realtime_data.get("realtime_protection_enabled", True)
        observed_evidence.append(f"Real-time protection enabled: {rt_enabled}.")

        # 4. Extract facts from Antivirus and Threat status
        threat_count = threat_data.get("threat_count", 0)
        has_threats = threat_data.get("has_threats", False)
        if has_threats:
            observed_evidence.append(f"Detected {threat_count} active/unresolved threat(s).")
        else:
            observed_evidence.append("No active threats detected.")

        # 5. Extract facts from Events
        event_count = events_data.get("count", 0)
        has_errors = events_data.get("has_errors", False)
        if has_errors:
            observed_evidence.append(f"Found {event_count} recent Defender event(s) including warning/error logs.")

        # 6. Evaluate scenario classification
        problem_category = "healthy"
        repair_available = False
        proposed_tool = None
        proposed_args = None

        if windefend_status == "STOPPED":
            if windefend_start == "DISABLED":
                problem_category = "service_disabled"
                interpretation.append("The Windows Defender service (WinDefend) is disabled and cannot start.")
                recommended_next_steps.append("Open Services management (services.msc) or Windows Security to re-enable Microsoft Defender.")
            else:
                problem_category = "service_stopped"
                interpretation.append("The Windows Defender service (WinDefend) is currently stopped.")
                recommended_next_steps.append("Restart the Windows Defender service (WinDefend) to restore active protection.")
                repair_available = True
                proposed_tool = "restart_defender_service"
                proposed_args = {}
        elif not rt_enabled:
            problem_category = "realtime_disabled"
            interpretation.append("Real-time protection is reported as disabled or not active.")
            recommended_next_steps.append("Open Windows Security settings (Windows Settings > Privacy & Security > Windows Security) and turn on Real-time protection.")
        elif has_threats:
            problem_category = "threats_detected"
            interpretation.append(f"Windows Defender has detected {threat_count} active threat(s) requiring user action.")
            recommended_next_steps.append("Open the Windows Security Center app to review and take action on the detected threats.")
        elif has_errors:
            problem_category = "recent_errors"
            interpretation.append("Recent warning or error events were logged for Windows Defender components.")
            recommended_next_steps.append("Restart the Windows Defender service to clear transient errors or review event log details.")
            repair_available = True
            proposed_tool = "restart_defender_service"
            proposed_args = {}
        else:
            problem_category = "healthy"
            interpretation.append("Microsoft Defender Antivirus service, real-time protection, and security health are operational.")
            recommended_next_steps.append("No immediate repair actions required.")

        summary = (
            f"Windows Defender Diagnosis ({problem_category}): {'; '.join(interpretation)}"
        )

        # 7. Record diagnostics in SQLite
        if session_id:
            try:
                self.diagnostic_repo.create_diagnostic_record(
                    session_id=session_id,
                    tool_name="get_defender_diagnostics",
                    category=problem_category,
                    raw_output=json.dumps(diag_data),
                    summary=summary,
                )
            except Exception as db_exc:
                logger.debug("Failed to record diagnostic in DB: %s", db_exc)

        return DefenderDiagnosis(
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
