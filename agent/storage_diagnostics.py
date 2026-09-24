"""Storage Diagnostics Orchestrator for WinFix AI (Phase 9).

Coordinates evidence collection across approved read-only storage diagnostic tools,
evaluates deterministic partition pressure thresholds, temporary storage occupancy,
and bounded large temporary file metrics.

Strictly read-only: NO storage modification or file deletion is performed in this module.
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

# Valid storage problem categories
STORAGE_CATEGORIES = {
    "low_disk_space",
    "temp_storage_pressure",
    "large_temp_files",
    "general_storage",
}


@dataclass
class StorageDiagnosis:
    """Structured, evidence-based storage diagnosis result."""

    problem_category: str
    summary: str
    observed_evidence: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)
    confidence: float = 0.8
    recommended_next_steps: List[str] = field(default_factory=list)
    repair_available: bool = False
    pressure_level: str = "NORMAL"
    target_drive: Optional[str] = None
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
            "pressure_level": self.pressure_level,
            "target_drive": self.target_drive,
            "tool_results": self.tool_results,
        }


class StorageDiagnosticsOrchestrator:
    """Coordinates read-only storage diagnostics, partition pressure evaluation, and evidence synthesis."""

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
    ) -> StorageDiagnosis:
        """Execute diagnostic storage tools and produce an evidence-backed diagnosis."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []
        category = "general_storage"
        repair_available = False
        target_drive: Optional[str] = None

        # 1. Execute Storage Pressure Analysis
        pressure_res = self.safety_engine.execute(
            tool_name="get_storage_pressure_analysis",
            session_id=session_id,
        )
        tool_results.append(pressure_res)

        # 2. Execute Temporary Storage Info
        temp_res = self.safety_engine.execute(
            tool_name="get_temp_storage_info",
            session_id=session_id,
        )
        tool_results.append(temp_res)

        # 3. Execute Large Temporary Files Analysis
        large_temp_res = self.safety_engine.execute(
            tool_name="analyze_large_temporary_files",
            arguments={"min_size_mb": 50.0, "limit": 10},
            session_id=session_id,
        )
        tool_results.append(large_temp_res)

        # 4. Extract Evidence
        overall_pressure = "NORMAL"
        if pressure_res.get("success") and pressure_res.get("data"):
            p_data = pressure_res["data"]
            overall_pressure = p_data.get("overall_pressure_level", "NORMAL")
            lowest_drive = p_data.get("lowest_free_drive")
            if lowest_drive:
                target_drive = lowest_drive.get("mountpoint")
                observed_evidence.append(
                    f"Volume '{lowest_drive.get('mountpoint')}' has {lowest_drive.get('free_formatted')} free "
                    f"({lowest_drive.get('percent_used')}% used, Pressure: {lowest_drive.get('pressure_level')})."
                )
            for v in p_data.get("volumes", []):
                if v.get("is_system_drive") and v != lowest_drive:
                    observed_evidence.append(
                        f"System drive '{v.get('mountpoint')}' has {v.get('free_formatted')} free ({v.get('percent_used')}% used)."
                    )

        temp_bytes = 0
        temp_formatted = "0 B"
        temp_files = 0
        if temp_res.get("success") and temp_res.get("data"):
            t_data = temp_res["data"]
            temp_bytes = t_data.get("total_temp_bytes", 0)
            temp_formatted = t_data.get("total_temp_formatted", "0 B")
            temp_files = t_data.get("total_temp_files", 0)
            locked_count = t_data.get("locked_or_inaccessible_files", 0)
            observed_evidence.append(
                f"Temporary storage directory contains {temp_files} file(s) occupying {temp_formatted} ({locked_count} locked/inaccessible)."
            )

        large_files_count = 0
        if large_temp_res.get("success") and large_temp_res.get("data"):
            l_data = large_temp_res["data"]
            large_files_count = l_data.get("large_files_found_count", 0)
            if large_files_count > 0:
                top_l = l_data.get("large_files", [])[0]
                observed_evidence.append(
                    f"Found {large_files_count} large temporary file(s) >= 50 MB (Largest: '{top_l.get('filename')}' at {top_l.get('size_formatted')})."
                )

        # 5. Categorize & Formulate Objective Interpretations
        if overall_pressure in ("CRITICAL", "HIGH"):
            category = "low_disk_space"
            interpretation.append(
                f"Storage volume capacity has reached {overall_pressure} pressure. Immediate space reclamation is recommended."
            )
            if temp_bytes > 100 * 1024 * 1024:  # > 100 MB
                recommended_next_steps.append("Purge obsolete user temporary files to reclaim storage capacity.")
                repair_available = True
            else:
                recommended_next_steps.append("Inspect installed applications and user documents for manual archival.")

        elif temp_bytes > 500 * 1024 * 1024:  # > 500 MB in temp
            category = "temp_storage_pressure"
            interpretation.append(
                f"User temporary storage has accumulated {temp_formatted} of cached and transient files."
            )
            recommended_next_steps.append("Clean user temporary cache directory.")
            repair_available = True

        elif large_files_count > 0:
            category = "large_temp_files"
            interpretation.append(
                f"Temporary directory contains {large_files_count} large file(s) that may no longer be required."
            )
            recommended_next_steps.append("Clean user temporary directory to purge obsolete large temporary files.")
            repair_available = True

        else:
            category = "general_storage"
            interpretation.append(
                f"Storage partitions are operating within normal capacity thresholds (Overall pressure: {overall_pressure})."
            )
            recommended_next_steps.append("No immediate storage cleanup actions required.")

        summary = f"Storage diagnosis completed: Category is {category.upper()} with {overall_pressure} pressure level."

        diagnosis = StorageDiagnosis(
            problem_category=category,
            summary=summary,
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.9 if repair_available else 0.8,
            recommended_next_steps=recommended_next_steps,
            repair_available=repair_available,
            pressure_level=overall_pressure,
            target_drive=target_drive,
            tool_results=tool_results,
        )

        # 6. Save to SQLite repository
        if session_id:
            try:
                self.diagnostic_repo.create(
                    session_id=session_id,
                    tool_name="storage_diagnostics",
                    raw_data=diagnosis.to_dict(),
                )
            except Exception as db_err:
                logger.debug("Failed saving storage diagnostic record to SQLite: %s", db_err)

        return diagnosis


# Default shared storage diagnostics orchestrator
default_storage_orchestrator = StorageDiagnosticsOrchestrator()
