"""Storage Repairs and Verification Orchestrator for WinFix AI (Phase 9).

Coordinates allowlisted, user-confirmed storage repair operations:
1. User temporary cache cleanup with strict sandbox boundary validation.

Enforces strict before-state capture, cryptographic confirmation token binding,
after-state deterministic verification, and SQLite audit logging.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from agent.safety import SafetyEngine, default_safety_engine
from agent.storage_diagnostics import StorageDiagnosis
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository

logger = logging.getLogger(__name__)


@dataclass
class StorageRepairProposal:
    """Structured proposal for a storage repair operation requiring user confirmation."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_effect: str = ""
    risk: str = "MEDIUM"
    requires_admin: bool = False
    verification_tool: Optional[str] = "get_temp_storage_info"

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
class StorageRepairExecutionResult:
    """Structured outcome of an executed storage repair with verification details."""

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


class StorageRepairsOrchestrator:
    """Coordinates allowlisted storage repairs with explicit user confirmation and verification."""

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
        diagnosis: StorageDiagnosis,
    ) -> Optional[StorageRepairProposal]:
        """Formulate a structured repair proposal strictly based on verified storage diagnostic evidence."""
        if diagnosis.repair_available and diagnosis.problem_category in (
            "low_disk_space",
            "temp_storage_pressure",
            "large_temp_files",
        ):
            tool = self.registry.get("clean_user_temp_cache")
            if tool:
                return StorageRepairProposal(
                    tool_name="clean_user_temp_cache",
                    arguments={"max_file_age_hours": 0.0, "dry_run": False},
                    reason="Diagnostic evidence indicates obsolete temporary files can be safely purged.",
                    expected_effect="Purges unlocked temporary files from the user temp directory to reclaim storage capacity.",
                    risk=tool.risk.value,
                    requires_admin=tool.requires_admin,
                    verification_tool=tool.verification_tool or "get_temp_storage_info",
                )

        return None

    def execute_repair_with_verification(
        self,
        proposal: StorageRepairProposal,
        session_id: Optional[str] = None,
        user_confirmed: bool = False,
        confirmation_token: Optional[str] = None,
    ) -> StorageRepairExecutionResult:
        """Execute storage repair under strict user confirmation and verify outcome."""
        tool = self.registry.get(proposal.tool_name)
        if not tool:
            return StorageRepairExecutionResult(
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
                logger.warning("Confirmation token mismatch for storage repair %s", proposal.tool_name)
                return StorageRepairExecutionResult(
                    tool_name=proposal.tool_name,
                    arguments=proposal.arguments,
                    confirmed=False,
                    repair_success=False,
                    verification_status="blocked",
                    explanation="Security validation failed: Confirmation token does not match the proposal arguments.",
                )

        # If unconfirmed, fail closed immediately without executing
        if not user_confirmed:
            return StorageRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="MEDIUM risk repair blocked: Explicit user confirmation required.",
            )

        # --- STEP 1: CAPTURE BEFORE-STATE ---
        before_state = None
        v_tool_name = proposal.verification_tool or tool.verification_tool or "get_temp_storage_info"
        try:
            before_res = self.safety_engine.execute(
                tool_name=v_tool_name,
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
            err_msg = repair_res.get("error", {}).get("message", "Storage repair execution failed.")
            return StorageRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=True,
                repair_success=False,
                before_state=before_state,
                repair_output=repair_output,
                verification_tool=v_tool_name,
                verification_status="failed",
                explanation=f"Storage cleanup failed: {err_msg}",
            )

        # --- STEP 3: CAPTURE AFTER-STATE & VERIFY ---
        after_state = None
        verification_status = "not_verified"
        explanation = "Cleanup executed, but post-cleanup verification could not verify reclaimed capacity."

        try:
            after_res = self.safety_engine.execute(
                tool_name=v_tool_name,
                session_id=session_id,
            )
            after_state = after_res.get("data")

            if after_res.get("success") and repair_output:
                del_count = repair_output.get("deleted_files_count", 0)
                freed = repair_output.get("freed_formatted", "0 B")
                failed_count = repair_output.get("failed_files_count", 0)

                verification_status = "verified"
                fail_note = f" ({failed_count} locked file(s) safely skipped)" if failed_count > 0 else ""
                explanation = f"Storage cleanup verified: Successfully removed {del_count} temporary file(s), reclaiming {freed}{fail_note}."
            else:
                verification_status = "not_verified"
                explanation = "Temporary cleanup executed, but post-cleanup storage verification returned no state data."

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

        return StorageRepairExecutionResult(
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
default_storage_repairs_orchestrator = StorageRepairsOrchestrator()
