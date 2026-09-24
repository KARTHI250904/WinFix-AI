"""Performance Diagnostics Orchestrator for WinFix AI (Phase 8).

Coordinates evidence collection across approved read-only performance diagnostic tools,
enforces evidence-based diagnosis (distinguishing observations from interpretations),
and integrates with SafetyEngine and SQLite persistence.

Strictly read-only: NO state-changing performance actions are performed in this module.
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

# Valid performance problem categories
PERFORMANCE_CATEGORIES = {
    "high_cpu",
    "high_memory",
    "disk_pressure",
    "process_issue",
    "general_performance",
}


@dataclass
class PerformanceDiagnosis:
    """Structured, evidence-based performance diagnosis result."""

    problem_category: str
    summary: str
    observed_evidence: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)
    confidence: float = 0.8
    recommended_next_steps: List[str] = field(default_factory=list)
    repair_available: bool = False
    suspected_pid: Optional[int] = None
    suspected_process_name: Optional[str] = None
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
            "suspected_pid": self.suspected_pid,
            "suspected_process_name": self.suspected_process_name,
            "tool_results": self.tool_results,
        }


class PerformanceDiagnosticsOrchestrator:
    """Coordinates read-only performance diagnostics, evidence collection, and synthesis."""

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
        suspected_pid: Optional[int] = None,
    ) -> PerformanceDiagnosis:
        """Execute diagnostic tools and produce an evidence-backed diagnosis."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []
        category = "general_performance"
        repair_available = False
        target_pid: Optional[int] = None
        target_name: Optional[str] = None

        # 1. Execute Snapshot Diagnostics
        snapshot_res = self.safety_engine.execute(
            tool_name="get_resource_snapshot",
            session_id=session_id,
        )
        tool_results.append(snapshot_res)

        cpu_res = self.safety_engine.execute(
            tool_name="get_cpu_diagnostics",
            session_id=session_id,
        )
        tool_results.append(cpu_res)

        mem_res = self.safety_engine.execute(
            tool_name="get_memory_diagnostics",
            session_id=session_id,
        )
        tool_results.append(mem_res)

        top_cpu_res = self.safety_engine.execute(
            tool_name="get_top_cpu_processes",
            arguments={"limit": 5},
            session_id=session_id,
        )
        tool_results.append(top_cpu_res)

        top_mem_res = self.safety_engine.execute(
            tool_name="get_top_memory_processes",
            arguments={"limit": 5},
            session_id=session_id,
        )
        tool_results.append(top_mem_res)

        temp_res = self.safety_engine.execute(
            tool_name="get_temp_storage_info",
            session_id=session_id,
        )
        tool_results.append(temp_res)

        # Process specific details if requested
        proc_detail_res = None
        if suspected_pid is not None and suspected_pid > 0:
            proc_detail_res = self.safety_engine.execute(
                tool_name="get_process_details",
                arguments={"pid": suspected_pid},
                session_id=session_id,
            )
            tool_results.append(proc_detail_res)

        # 2. Extract Evidence
        cpu_pct = 0.0
        if cpu_res.get("success") and cpu_res.get("data"):
            cpu_pct = cpu_res["data"].get("overall_percent", 0.0)
            observed_evidence.append(f"Overall CPU utilization is currently at {cpu_pct}%.")

        mem_pct = 0.0
        mem_avail = "Unknown"
        if mem_res.get("success") and mem_res.get("data"):
            vmem = mem_res["data"].get("virtual_memory", {})
            mem_pct = vmem.get("percent_used", 0.0)
            mem_avail = vmem.get("available_formatted", "Unknown")
            observed_evidence.append(
                f"Physical RAM utilization is at {mem_pct}% (Available: {mem_avail})."
            )

        top_cpu_procs = []
        if top_cpu_res.get("success") and top_cpu_res.get("data"):
            top_cpu_procs = top_cpu_res["data"].get("processes", [])
            if top_cpu_procs:
                top_p = top_cpu_procs[0]
                observed_evidence.append(
                    f"Top CPU consumer: {top_p.get('name')} (PID {top_p.get('pid')}) using {top_p.get('cpu_percent')}% CPU."
                )

        top_mem_procs = []
        if top_mem_res.get("success") and top_mem_res.get("data"):
            top_mem_procs = top_mem_res["data"].get("processes", [])
            if top_mem_procs:
                top_m = top_mem_procs[0]
                observed_evidence.append(
                    f"Top Memory consumer: {top_m.get('name')} (PID {top_m.get('pid')}) using {top_m.get('memory_formatted')} RAM."
                )

        temp_bytes = 0
        temp_formatted = "0 B"
        if temp_res.get("success") and temp_res.get("data"):
            temp_bytes = temp_res["data"].get("total_temp_bytes", 0)
            temp_formatted = temp_res["data"].get("total_temp_formatted", "0 B")
            temp_files = temp_res["data"].get("total_temp_files", 0)
            observed_evidence.append(
                f"User temporary cache contains {temp_files} file(s) occupying {temp_formatted}."
            )

        # If a specific PID was inspected
        if proc_detail_res and proc_detail_res.get("success") and proc_detail_res.get("data"):
            p_data = proc_detail_res["data"]
            target_pid = p_data.get("pid")
            target_name = p_data.get("name")
            observed_evidence.append(
                f"Target process '{target_name}' (PID {target_pid}) inspected: Status={p_data.get('status')}, "
                f"CPU={p_data.get('cpu_percent')}%, Memory={p_data.get('memory_rss_formatted')}."
            )

        # 3. Categorize & Interpret (Objective Terminology)
        # Check High CPU
        if cpu_pct >= 85.0 or (top_cpu_procs and top_cpu_procs[0].get("cpu_percent", 0.0) >= 50.0):
            category = "high_cpu"
            culprit = top_cpu_procs[0] if top_cpu_procs else None
            if culprit:
                target_pid = culprit.get("pid")
                target_name = culprit.get("name")
                interpretation.append(
                    f"Process '{target_name}' (PID {target_pid}) is exerting sustained high CPU load ({culprit.get('cpu_percent')}%)."
                )
                recommended_next_steps.append(f"Consider terminating runaway process '{target_name}' (PID {target_pid}).")
                repair_available = True
            else:
                interpretation.append("System is experiencing severe CPU contention across multiple background tasks.")

        # Check High Memory
        elif mem_pct >= 85.0 or (top_mem_procs and top_mem_procs[0].get("memory_percent", 0.0) >= 40.0):
            category = "high_memory"
            culprit = top_mem_procs[0] if top_mem_procs else None
            if culprit:
                target_pid = culprit.get("pid")
                target_name = culprit.get("name")
                interpretation.append(
                    f"Process '{target_name}' (PID {target_pid}) is consuming substantial physical RAM ({culprit.get('memory_formatted')})."
                )
                recommended_next_steps.append(f"Evaluate terminating memory-heavy process '{target_name}' (PID {target_pid}).")
                repair_available = True
            else:
                interpretation.append("System is under acute memory pressure.")

        # Check Disk / Temp Cache Pressure
        elif temp_bytes > 500 * 1024 * 1024:  # > 500 MB in temp
            category = "disk_pressure"
            interpretation.append(f"User temporary cache is accumulating obsolete files ({temp_formatted}).")
            recommended_next_steps.append("Clean user temporary cache to free up disk storage.")
            repair_available = True

        else:
            category = "general_performance"
            interpretation.append("System resource utilization (CPU, RAM, and Disk) is currently operating within normal parameters.")
            recommended_next_steps.append("No immediate performance repairs required.")

        summary = f"Performance diagnosis completed: Category is {category.upper()} with {len(observed_evidence)} observations."

        diagnosis = PerformanceDiagnosis(
            problem_category=category,
            summary=summary,
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.9 if repair_available else 0.8,
            recommended_next_steps=recommended_next_steps,
            repair_available=repair_available,
            suspected_pid=target_pid,
            suspected_process_name=target_name,
            tool_results=tool_results,
        )

        # 4. Save to SQLite repository
        if session_id:
            try:
                self.diagnostic_repo.create(
                    session_id=session_id,
                    tool_name="performance_diagnostics",
                    raw_data=diagnosis.to_dict(),
                )
            except Exception as db_err:
                logger.debug("Failed saving diagnostic record to SQLite: %s", db_err)

        return diagnosis


# Default shared performance diagnostics orchestrator
default_performance_orchestrator = PerformanceDiagnosticsOrchestrator()
