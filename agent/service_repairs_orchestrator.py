"""Windows Services Repairs and Verification Orchestrator for WinFix AI (Phase 10).

Coordinates allowlisted, user-confirmed service repair operations:
1. start_service (start an approved stopped service)
2. stop_service (gracefully stop an approved non-critical service)
3. restart_service (restart an approved non-critical service)

Enforces strict before-state capture, cryptographic SHA-256 confirmation token binding,
protected-service verification, after-state deterministic verification, and SQLite audit logging.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from agent.safety import SafetyEngine, default_safety_engine
from agent.service_diagnostics import ServiceDiagnosis
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
from windows.service_repairs import is_service_stop_protected

logger = logging.getLogger(__name__)


@dataclass
class ServiceRepairProposal:
    """Structured proposal for a service repair operation requiring user confirmation."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    service_name: str = ""
    display_name: str = ""
    reason: str = ""
    expected_effect: str = ""
    risk: str = "MEDIUM"
    requires_admin: bool = True
    verification_tool: Optional[str] = "get_service_status"

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
class ServiceRepairExecutionResult:
    """Structured outcome of an executed service repair with verification details."""

    tool_name: str
    arguments: Dict[str, Any]
    confirmed: bool
    repair_success: bool
    before_state: Optional[Dict[str, Any]] = None
    repair_output: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    verification_tool: Optional[str] = "get_service_status"
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


class ServiceRepairsOrchestrator:
    """Coordinates allowlisted service repairs with explicit user confirmation and verification."""

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
        self.execution_repo = ToolExecutionRepository(self.db_manager)
        self.solution_repo = SolutionRepository(self.db_manager)

    def validate_confirmation_token(
        self,
        token: str,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> bool:
        """Verify that the provided confirmation token strictly matches tool, arguments, and session."""
        expected = hashlib.sha256(
            f"{tool_name}:{json.dumps(arguments, sort_keys=True)}:{session_id or ''}".encode("utf-8")
        ).hexdigest()
        return token == expected

    def prepare_repair_proposal(
        self,
        diagnosis: ServiceDiagnosis,
        session_id: Optional[str] = None,
    ) -> Optional[ServiceRepairProposal]:
        """Construct an exact confirmation-bound repair proposal if an approved repair is available."""
        if not diagnosis.repair_available or not diagnosis.proposed_tool or not diagnosis.target_service:
            return None

        tool_name = diagnosis.proposed_tool
        s_name = diagnosis.target_service
        args = diagnosis.proposed_args or {"service_name": s_name}

        if tool_name == "start_service":
            return ServiceRepairProposal(
                tool_name="start_service",
                arguments=args,
                service_name=s_name,
                display_name=s_name,
                reason=f"Service '{s_name}' is stopped and needs to be started.",
                expected_effect=f"Transition service '{s_name}' state to RUNNING.",
                risk="MEDIUM",
                requires_admin=True,
                verification_tool="get_service_status",
            )
        elif tool_name == "stop_service":
            is_prot, reason = is_service_stop_protected(s_name)
            if is_prot:
                return None
            return ServiceRepairProposal(
                tool_name="stop_service",
                arguments=args,
                service_name=s_name,
                display_name=s_name,
                reason=f"Stop service '{s_name}' as requested.",
                expected_effect=f"Transition service '{s_name}' state to STOPPED.",
                risk="MEDIUM",
                requires_admin=True,
                verification_tool="get_service_status",
            )
        elif tool_name == "restart_service":
            is_prot, reason = is_service_stop_protected(s_name)
            if is_prot:
                return None
            return ServiceRepairProposal(
                tool_name="restart_service",
                arguments=args,
                service_name=s_name,
                display_name=s_name,
                reason=f"Restart service '{s_name}' to recover operational state.",
                expected_effect=f"Stop and restart service '{s_name}', restoring RUNNING state.",
                risk="MEDIUM",
                requires_admin=True,
                verification_tool="get_service_status",
            )

        return None

    def execute_confirmed_repair(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        confirmation_token: str,
        session_id: Optional[str] = None,
    ) -> ServiceRepairExecutionResult:
        """Execute an approved service repair after validating the confirmation token."""
        # 1. Token validation
        if not self.validate_confirmation_token(confirmation_token, tool_name, arguments, session_id):
            logger.warning("Rejected unconfirmed or tampered service repair token for %s", tool_name)
            return ServiceRepairExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="Execution blocked: Confirmation token is invalid or does not match parameters/session.",
            )

        # 2. Allowlist tool check
        allowed_tools = {"start_service", "stop_service", "restart_service"}
        if tool_name not in allowed_tools:
            return ServiceRepairExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                confirmed=True,
                repair_success=False,
                verification_status="blocked",
                explanation=f"Execution blocked: Tool '{tool_name}' is not an approved service repair tool.",
            )

        service_name = arguments.get("service_name", "")

        # 3. Protected service check for stop/restart
        if tool_name in {"stop_service", "restart_service"}:
            is_prot, prot_reason = is_service_stop_protected(service_name)
            if is_prot:
                return ServiceRepairExecutionResult(
                    tool_name=tool_name,
                    arguments=arguments,
                    confirmed=True,
                    repair_success=False,
                    verification_status="blocked",
                    explanation=f"Execution blocked: {prot_reason}",
                )

        # 4. Capture Before-State
        before_res = self.safety_engine.execute(
            tool_name="get_service_status",
            arguments={"service_name": service_name},
            session_id=session_id,
        )
        before_state = before_res.get("data") if before_res["success"] else None

        # 5. Execute Repair Tool
        repair_res = self.safety_engine.execute(
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
        )
        repair_success = repair_res.get("success", False)
        repair_output = repair_res.get("data")

        # 6. Capture After-State (Verification)
        after_res = self.safety_engine.execute(
            tool_name="get_service_status",
            arguments={"service_name": service_name},
            session_id=session_id,
        )
        after_state = after_res.get("data") if after_res["success"] else None

        # 7. Evaluate Verification Status
        verification_status = "not_verified"
        explanation = ""

        if not repair_success:
            err = repair_res.get("error", {})
            verification_status = "failed"
            explanation = f"Service repair '{tool_name}' failed: {err.get('message', 'Unknown error')}."
        elif after_state:
            curr_status = after_state.get("status", "UNKNOWN")
            if tool_name == "start_service":
                if curr_status == "RUNNING":
                    verification_status = "verified"
                    explanation = f"Service '{service_name}' started successfully and verified RUNNING."
                else:
                    verification_status = "not_verified"
                    explanation = f"Service '{service_name}' start executed but status is {curr_status}."
            elif tool_name == "stop_service":
                if curr_status == "STOPPED":
                    verification_status = "verified"
                    explanation = f"Service '{service_name}' stopped successfully and verified STOPPED."
                else:
                    verification_status = "not_verified"
                    explanation = f"Service '{service_name}' stop executed but status is {curr_status}."
            elif tool_name == "restart_service":
                if curr_status == "RUNNING":
                    verification_status = "verified"
                    explanation = f"Service '{service_name}' restarted successfully and verified RUNNING."
                else:
                    verification_status = "not_verified"
                    explanation = f"Service '{service_name}' restart executed but status is {curr_status}."
        else:
            verification_status = "not_verified"
            explanation = "Unable to query service status following repair."

        # 8. Record audit log in SQLite repository
        try:
            if session_id:
                self.solution_repo.create(
                    session_id=session_id,
                    proposed_repair=f"{tool_name} ({service_name})",
                    repair_executed=True,
                    verified_status=verification_status,
                    verification_notes=explanation,
                )
        except Exception as audit_exc:
            logger.error("Failed to audit service repair in database: %s", audit_exc)


        return ServiceRepairExecutionResult(
            tool_name=tool_name,
            arguments=arguments,
            confirmed=True,
            repair_success=repair_success,
            before_state=before_state,
            repair_output=repair_output,
            after_state=after_state,
            verification_tool="get_service_status",
            verification_status=verification_status,
            explanation=explanation,
        )
