"""Windows Application Crash Diagnostics Orchestrator for WinFix AI (Phase 14).

Coordinates evidence collection across approved read-only Windows Application Crash diagnostic tools,
evaluates crash frequency, recurring applications, faulting modules, exception codes, and WER status.

Strictly read-only: NO process killing, automatic application restarts, DLL modifications, or registry writes.
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

CRASH_CATEGORIES = {
    "NO_RECENT_CRASH_EVIDENCE",
    "RECENT_APPLICATION_CRASH",
    "RECURRING_APPLICATION_CRASH",
    "FAULTING_MODULE_OBSERVED",
    "WER_EVIDENCE_AVAILABLE",
    "INSUFFICIENT_EVIDENCE",
    "DATA_UNAVAILABLE",
}


@dataclass
class ApplicationCrashDiagnosis:
    """Structured, evidence-based Windows Application Crash diagnosis result."""

    problem_category: str
    summary: str
    observed_evidence: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)
    confidence: float = 0.8
    recommended_next_steps: List[str] = field(default_factory=list)
    repair_available: bool = False  # Phase 14 is strictly diagnostic: 0 repairs
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


class ApplicationCrashDiagnosticsOrchestrator:
    """Coordinates read-only Windows Application Crash diagnostics and scenario analysis."""

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
        time_window: str = "24h",
    ) -> ApplicationCrashDiagnosis:
        """Execute read-only Application Crash diagnostic tools and synthesize findings."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []

        # 1. Execute unified diagnostic aggregator
        diag_res = self.safety_engine.execute(
            tool_name="get_application_crash_diagnostics",
            arguments={"time_window": time_window},
            session_id=session_id,
        )
        tool_results.append(diag_res)

        if not diag_res.get("success"):
            return ApplicationCrashDiagnosis(
                problem_category="DATA_UNAVAILABLE",
                summary="Failed to execute Windows Application Crash diagnostics.",
                observed_evidence=["Diagnostic tool returned an error or is unsupported on this platform."],
                interpretation=["Unable to inspect Windows Application Event log reliably."],
                confidence=0.2,
                recommended_next_steps=["Verify Windows operating system and event log service status."],
                repair_available=False,
                tool_results=tool_results,
            )

        diag_data = diag_res.get("data", {})
        total_crashes = diag_data.get("total_crashes", 0)
        overall_status = diag_data.get("overall_status", "NO_RECENT_CRASH_EVIDENCE")
        summary_data = diag_data.get("summary") or {}
        frequency_data = diag_data.get("frequency") or {}
        faulting_modules = diag_data.get("faulting_modules") or []
        wer_status = diag_data.get("wer_status") or {}
        raw_evidence = diag_data.get("evidence") or []
        raw_recs = diag_data.get("recommendations") or []

        # 2. Extract facts from evidence payload
        observed_evidence.extend(raw_evidence)

        recurring_apps = summary_data.get("recurring_applications", [])
        recurring_mods = summary_data.get("recurring_modules", [])

        # 3. Categorization and interpretation
        problem_category = overall_status
        if total_crashes == 0:
            problem_category = "NO_RECENT_CRASH_EVIDENCE"
            interpretation.append(f"No application crash or hang events were logged within the past {time_window}.")
            recommended_next_steps.append("No immediate application troubleshooting required.")
        elif recurring_apps:
            problem_category = "RECURRING_APPLICATION_CRASH"
            apps_str = ", ".join(recurring_apps)
            interpretation.append(f"Multiple repeated crash events detected for: {apps_str}.")
            for app in recurring_apps:
                recommended_next_steps.append(f"Check for available updates or patches for application '{app}'.")
                recommended_next_steps.append(f"Review '{app}' configuration or reinstall if instability continues.")
        elif faulting_modules:
            problem_category = "FAULTING_MODULE_OBSERVED"
            mod_names = [m.get("module_name") for m in faulting_modules if m.get("module_name")]
            interpretation.append(f"Application crashes were associated with module(s): {', '.join(mod_names)}.")
            recommended_next_steps.append("Check if the faulting module is part of the application or a third-party plugin/driver.")
        else:
            problem_category = "RECENT_APPLICATION_CRASH"
            interpretation.append(f"Found {total_crashes} isolated crash event(s) within {time_window}.")
            recommended_next_steps.append("Monitor application behavior to see if crashes recur.")

        if wer_status.get("status") == "OPERATIONAL":
            observed_evidence.append("Windows Error Reporting is operational and capturing diagnostic telemetry.")

        summary = (
            f"Application Crash Diagnosis ({problem_category}): {'; '.join(interpretation)}"
        )

        # 4. Record diagnostics in SQLite
        if session_id:
            try:
                self.diagnostic_repo.create_diagnostic_record(
                    session_id=session_id,
                    tool_name="get_application_crash_diagnostics",
                    category=problem_category,
                    raw_output=json.dumps(diag_data),
                    summary=summary,
                )
            except Exception as db_exc:
                logger.debug("Failed to record application crash diagnostic in DB: %s", db_exc)

        return ApplicationCrashDiagnosis(
            problem_category=problem_category,
            summary=summary,
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.9,
            recommended_next_steps=recommended_next_steps,
            repair_available=False,
            proposed_tool=None,
            proposed_args=None,
            tool_results=tool_results,
        )


default_application_crash_orchestrator = ApplicationCrashDiagnosticsOrchestrator()

