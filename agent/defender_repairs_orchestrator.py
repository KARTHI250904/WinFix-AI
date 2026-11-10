"""Windows Defender Repairs and Verification Orchestrator for WinFix AI (Phase 13).

Coordinates allowlisted, user-confirmed Windows Defender repair operations:
1. restart_defender_service (restart Windows Defender service 'WinDefend')

Enforces strict before-state capture, cryptographic SHA-256 confirmation token binding,
after-state deterministic verification, and SQLite audit logging.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from agent.defender_diagnostics import DefenderDiagnosis
from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
from windows.windows_defender_repairs import DEFENDER_SERVICE_NAME

logger = logging.getLogger(__name__)


@dataclass
class DefenderRepairProposal:
    """Structured proposal for a Windows Defender repair operation requiring user confirmation."""

    tool_name: str = "restart_defender_service"
    arguments: Dict[str, Any] = field(default_factory=dict)
    service_name: str = DEFENDER_SERVICE_NAME
    display_name: str = "Microsoft Defender Antivirus Service"
    reason: str = "Restart the Microsoft Defender Antivirus service (WinDefend) to restore active protection."
    expected_effect: str = "Stop and restart 'WinDefend', restoring RUNNING state and re-engaging Defender protection."
    risk: str = "MEDIUM"
    requires_admin: bool = True
    verification_tool: Optional[str] = "get_defender_service_status"

    def generate_confirmation_token(self, session_id: Optional[str] = None) -> str:
        """Generate a cryptographic confirmation token bound to tool, arguments, and session."""
        raw = f"{self.tool_name}:{json.dumps(self.arguments, sort_keys=True)}:{session_id or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Serialize proposal to dictionary including bound confirmation token."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "service_name": self.service_name,
            "display_name": self.display_name,
            "reason": self.reason,
            "expected_effect": self.expected_effect,
            "risk": self.risk,
            "requires_admin": self.requires_admin,
            "verification_tool": self.verification_tool,
            "confirmation_token": self.generate_confirmation_token(session_id),
        }


@dataclass
class DefenderRepairExecutionResult:
    """Structured outcome of an executed Windows Defender repair with verification details."""

    tool_name: str
    arguments: Dict[str, Any]
    confirmed: bool
    repair_success: bool
    before_state: Optional[Dict[str, Any]] = None
    repair_output: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    verification_tool: Optional[str] = "get_defender_service_status"
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


class DefenderRepairsOrchestrator:
    """Coordinates allowlisted Windows Defender repairs with explicit user confirmation and verification."""

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
        self.tool_exec_repo = ToolExecutionRepository(self.db_manager)
        self.solution_repo = SolutionRepository(self.db_manager)

    def prepare_restart_proposal(
        self,
        session_id: Optional[str] = None,
        diagnosis: Optional[DefenderDiagnosis] = None,
    ) -> DefenderRepairProposal:
        """Create a structured proposal for restarting the Windows Defender service."""
        reason = "Restart the Windows Defender service (WinDefend) to reinitialize protection engine."
        if diagnosis and diagnosis.summary:
            reason = f"Based on diagnosis: {diagnosis.summary}"

        return DefenderRepairProposal(
            tool_name="restart_defender_service",
            arguments={},
            service_name=DEFENDER_SERVICE_NAME,
            display_name="Microsoft Defender Antivirus Service",
            reason=reason,
            expected_effect="Sequential stop and restart of 'WinDefend', restoring RUNNING state.",
            risk="MEDIUM",
            requires_admin=True,
            verification_tool="get_defender_service_status",
        )

    def execute_confirmed_restart(
        self,
        proposal: DefenderRepairProposal,
        user_confirmed_token: str,
        session_id: Optional[str] = None,
    ) -> DefenderRepairExecutionResult:
        """Execute the confirmed Windows Defender service restart with verification and SQLite audit logging."""
        # 1. Enforce mandatory, non-empty confirmation token
        if not user_confirmed_token or not isinstance(user_confirmed_token, str) or not user_confirmed_token.strip():
            logger.warning("Missing or empty confirmation token for Windows Defender repair %s", proposal.tool_name)
            return DefenderRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="Security validation failed: Mandatory confirmation token missing or empty.",
            )

        # 2. Cryptographic confirmation token validation
        expected_token = proposal.generate_confirmation_token(session_id)
        if user_confirmed_token != expected_token:
            logger.warning("Confirmation token mismatch for Windows Defender repair %s", proposal.tool_name)
            return DefenderRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="Security validation failed: Confirmation token does not match the proposal arguments.",
            )

        # 3. Capture Before-State
        before_res = self.safety_engine.execute(
            tool_name="get_defender_service_status",
            arguments={},
            session_id=session_id,
        )
        before_state = before_res.get("data") if before_res.get("success") else None

        # 4. Execute controlled repair through SafetyEngine
        repair_res = self.safety_engine.execute(
            tool_name=proposal.tool_name,
            arguments=proposal.arguments,
            session_id=session_id,
            user_confirmed=True,
            confirmation_token=user_confirmed_token,
        )

        repair_success = bool(repair_res.get("success"))
        repair_output = repair_res.get("data")
        repair_error = repair_res.get("error")

        if not repair_success and repair_error and repair_error.get("code") in ("TOKEN_ALREADY_USED", "TOKEN_REQUIRED", "SAFETY_BLOCKED", "CONFIRMATION_REQUIRED"):
            return DefenderRepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation=repair_error.get("message", "Operation blocked."),
                before_state=before_state,
            )

        # 4. Capture After-State via verification tool
        after_res = self.safety_engine.execute(
            tool_name="get_defender_service_status",
            arguments={},
            session_id=session_id,
        )
        after_state = after_res.get("data") if after_res.get("success") else None

        # 5. Determine deterministic verification status
        verification_status = "not_verified"
        if repair_success and after_state and after_state.get("status") == "RUNNING":
            verification_status = "verified"
            explanation = "Windows Defender service ('WinDefend') successfully restarted and verified in RUNNING state."
        else:
            verification_status = "not_verified"
            err_msg = repair_error.get("message") if repair_error else "Service did not reach RUNNING state."
            explanation = f"Windows Defender repair failed or could not be verified: {err_msg}"

        # 6. Record in SQLite audit tables
        if session_id:
            try:
                self.solution_repo.create_solution(
                    session_id=session_id,
                    tool_name=proposal.tool_name,
                    parameters=proposal.arguments,
                    success=repair_success and (verification_status == "verified"),
                    verified=(verification_status == "verified"),
                    verification_output=after_state,
                    error_message=str(repair_error) if repair_error else None,
                )
            except Exception as audit_exc:
                logger.debug("Failed to record Windows Defender repair audit record: %s", audit_exc)

        return DefenderRepairExecutionResult(
            tool_name=proposal.tool_name,
            arguments=proposal.arguments,
            confirmed=True,
            repair_success=repair_success,
            before_state=before_state,
            repair_output=repair_output,
            after_state=after_state,
            verification_tool="get_defender_service_status",
            verification_status=verification_status,
            explanation=explanation,
        )
