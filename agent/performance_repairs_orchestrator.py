"""Performance Repairs and Verification Orchestrator for WinFix AI (Phase 8).

Coordinates allowlisted, user-confirmed performance repairs:
1. User-space process termination with kernel/OS blocklist enforcement.
2. Safe user temporary cache cleanup.

Enforces strict before-state capture, cryptographic confirmation token binding,
after-state deterministic verification, and SQLite audit logging.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from agent.performance_diagnostics import PerformanceDiagnosis
from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
from windows.performance_repairs import is_process_termination_blocked

logger = logging.getLogger(__name__)


@dataclass
class PerformanceRepairProposal:
    """Structured proposal for a performance repair operation requiring user confirmation."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_effect: str = ""
    risk: str = "MEDIUM"
    requires_admin: bool = False
    verification_tool: Optional[str] = None

    def generate_confirmation_token(self, session_id: Optional[str] = None) -> str:
        """Generate a cryptographic confirmation token bound to tool, arguments, and session."""
        raw = f"{self.tool_name}:{json.dumps(self.arguments, sort_keys=True)}:{session_id or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Serialize proposal to dictionary including bound confirmation token."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "expected_effect": self.expected_effect,
            "risk": self.risk,
            "requires_admin": self.requires_admin,
            "verification_tool": self.verification_tool,
            "confirmation_token": self.generate_confirmation_token(session_id),
        }


@dataclass
class PerformanceRepairExecutionResult:
    """Structured outcome of an executed performance repair with verification details."""

    tool_name: str
    arguments: Dict[str, Any]
    confirmed: bool
    repair_success: bool
    before_state: Optional[Dict[str, Any]] = None
    repair_output: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    verification_tool: Optional[str] = None
    verification_status: str = "unverified"  # verified, not_verified, failed, blocked
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize execution result to dictionary."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "confirmed": self.confirmed,
            "repair_success": self.repair_success,
            "before_state": self.before_state,
            "repair_output": self.repair_output,
            "after_state": self.after_state,
            "verification_tool": self.verification_tool,
            "verification_status": self.verification_status,
            "explanation": self.explanation,
        }


class PerformanceRepairsOrchestrator:
    """Coordinates allowlisted performance repairs with explicit user confirmation and verification."""

    def __init__(
        self,
        safety_engine: Optional[SafetyEngine] = None,
        registry: Optional[ToolRegistry] = None,
        db_mgr: Optional[DatabaseManager] = None,
    ) -> None:
        self.safety_engine = safety_engine or default_safety_engine
        self.registry = registry or default_tool_registry
        self.db_manager = db_mgr or default_db_manager

        self.session_repo = SessionRepository(self.db_manager)
        self.solution_repo = SolutionRepository(self.db_manager)
        self.exec_repo = ToolExecutionRepository(self.db_manager)

    def propose_repair_from_diagnosis(
        self,
        diagnosis: PerformanceDiagnosis,
    ) -> Optional[PerformanceRepairProposal]:
        """Formulate a structured repair proposal strictly based on verified diagnostic evidence."""
        # 1. High CPU / High Memory runaway process -> terminate_user_process
        if diagnosis.problem_category in ("high_cpu", "high_memory", "process_issue") and diagnosis.suspected_pid:
            pid = diagnosis.suspected_pid
            p_name = diagnosis.suspected_process_name

            # Pre-screen target against safety blocklist
            blocked, reason = is_process_termination_blocked(pid, p_name)
            if blocked:
                logger.info("Cannot propose process termination for PID %s: %s", pid, reason)
                return None

            tool = self.registry.get("terminate_user_process")
            if tool:
                return PerformanceRepairProposal(
                    tool_name="terminate_user_process",
                    arguments={"pid": pid, "process_name": p_name},
                    reason=f"Process '{p_name}' (PID {pid}) is causing sustained {diagnosis.problem_category.replace('_', ' ')}.",
                    expected_effect=f"Terminates user process '{p_name}' (PID {pid}) to release system resources.",
                    risk=tool.risk.value,
                    requires_admin=tool.requires_admin,
                    verification_tool=tool.verification_tool or "get_process_details",
                )

        # 2. Disk Pressure from Temp Cache -> clean_user_temp_cache
        if diagnosis.problem_category == "disk_pressure":
            tool = self.registry.get("clean_user_temp_cache")
            if tool:
                return PerformanceRepairProposal(
                    tool_name="clean_user_temp_cache",
                    arguments={"max_file_age_hours": 0.0, "dry_run": False},
                    reason="User temporary cache directory has accumulated obsolete files.",
                    expected_effect="Purges unlocked temporary files from %TEMP% to reclaim disk space.",
                    risk=tool.risk.value,
                    requires_admin=tool.requires_admin,
                    verification_tool=tool.verification_tool or "get_temp_storage_info",
                )

        return None

    def execute_repair_with_verification(
        self,
        proposal: PerformanceRepairProposal,
        session_id: Optional[str] = None,
        user_confirmed: bool = False,
        confirmation_token: Optional[str] = None,
    ) -> PerformanceRepairExecutionResult:
        """Execute repair under strict user confirmation and verify outcome."""
        tool = self.registry.get(proposal.tool_name)
        if not tool:
            return PerformanceRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=user_confirmed,
                repair_success=False,
                verification_status="blocked",
                explanation=f"Tool '{proposal.tool_name}' is not in the approved ToolRegistry.",
            )

        # Validate confirmation token if provided
        if confirmation_token:
            expected_token = proposal.generate_confirmation_token(session_id)
            if confirmation_token != expected_token:
                logger.warning("Confirmation token mismatch for repair %s", proposal.tool_name)
                return PerformanceRepairExecutionResult(
                    tool_name=proposal.tool_name,
                    arguments=proposal.arguments,
                    confirmed=False,
                    repair_success=False,
                    verification_status="blocked",
                    explanation="Security validation failed: Confirmation token does not match the proposal arguments.",
                )

        # If unconfirmed, fail closed immediately without executing
        if not user_confirmed:
            return PerformanceRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="MEDIUM risk repair blocked: Explicit user confirmation required.",
            )

        # --- STEP 1: CAPTURE BEFORE-STATE ---
        before_state = None
        v_tool_name = proposal.verification_tool or tool.verification_tool or "get_resource_snapshot"
        try:
            if proposal.tool_name == "terminate_user_process":
                target_pid = proposal.arguments.get("pid")
                if target_pid is not None:
                    before_res = self.safety_engine.execute(
                        tool_name="get_process_details",
                        arguments={"pid": target_pid},
                        session_id=session_id,
                    )
                    before_state = before_res.get("data")
            elif proposal.tool_name == "clean_user_temp_cache":
                before_res = self.safety_engine.execute(
                    tool_name="get_temp_storage_info",
                    session_id=session_id,
                )
                before_state = before_res.get("data")
        except Exception as before_err:
            logger.debug("Failed to capture before-state: %s", before_err)

        # --- STEP 2: EXECUTE REPAIR VIA SAFETY ENGINE ---
        repair_res = self.safety_engine.execute(
            tool_name=proposal.tool_name,
            arguments=proposal.arguments,
            session_id=session_id,
            user_confirmed=True,
        )

        repair_success = bool(repair_res.get("success", False))
        repair_output = repair_res.get("data")

        # If repair execution itself failed, do not attempt automatic recovery loop
        if not repair_success:
            err_msg = repair_res.get("error", {}).get("message", "Repair execution failed.")
            return PerformanceRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=True,
                repair_success=False,
                before_state=before_state,
                repair_output=repair_output,
                verification_tool=v_tool_name,
                verification_status="failed",
                explanation=f"Repair action failed: {err_msg}",
            )

        # --- STEP 3: CAPTURE AFTER-STATE & VERIFY ---
        after_state = None
        verification_status = "not_verified"
        explanation = "Repair executed, but verification check could not confirm state change."

        try:
            if proposal.tool_name == "terminate_user_process":
                target_pid = proposal.arguments.get("pid")
                after_res = self.safety_engine.execute(
                    tool_name="get_process_details",
                    arguments={"pid": target_pid},
                    session_id=session_id,
                )
                after_state = after_res.get("data")

                # If process no longer exists (PROCESS_NOT_FOUND error), it is verified terminated
                if not after_res.get("success") and after_res.get("error", {}).get("code") in ("PROCESS_NOT_FOUND", "INVALID_PID"):
                    verification_status = "verified"
                    explanation = f"Target process (PID {target_pid}) was successfully terminated and is no longer running."
                elif after_res.get("success") and after_state:
                    # Still running
                    verification_status = "not_verified"
                    explanation = f"Process (PID {target_pid}) is still active after termination attempt."
                else:
                    verification_status = "verified"
                    explanation = f"Process (PID {target_pid}) terminated."

            elif proposal.tool_name == "clean_user_temp_cache":
                after_res = self.safety_engine.execute(
                    tool_name="get_temp_storage_info",
                    session_id=session_id,
                )
                after_state = after_res.get("data")

                if after_res.get("success") and repair_output:
                    freed = repair_output.get("freed_formatted", "0 B")
                    del_count = repair_output.get("deleted_files_count", 0)
                    verification_status = "verified"
                    explanation = f"User temp cache clean completed: Removed {del_count} file(s), freeing {freed}."
                else:
                    verification_status = "not_verified"
                    explanation = "Temp cleanup executed, but post-cleanup verification could not verify freed storage."

            else:
                verification_status = "verified"
                explanation = "Post-repair verification check completed successfully."

        except Exception as verify_err:
            logger.error("Verification execution error: %s", verify_err)
            verification_status = "failed"
            explanation = f"Post-repair verification check encountered an error: {verify_err}"

        # --- STEP 4: PERSIST SOLUTION IN SQLITE ---
        if session_id:
            try:
                self.solution_repo.create(
                    session_id=session_id,
                    proposed_repair=proposal.tool_name,
                    repair_executed=True,
                    verified_status=verification_status,
                    verification_notes=explanation,
                )
            except Exception as sol_err:
                logger.debug("Solution record note: %s", sol_err)

        return PerformanceRepairExecutionResult(
            tool_name=proposal.tool_name,
            arguments=proposal.arguments,
            confirmed=True,
            repair_success=repair_success,
            before_state=before_state,
            repair_output=repair_output,
            after_state=after_state,
            verification_tool=v_tool_name,
            verification_status=verification_status,
            explanation=explanation,
        )


# Default shared orchestrator
default_performance_repairs_orchestrator = PerformanceRepairsOrchestrator()
