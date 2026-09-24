"""Bluetooth Repairs and Verification Orchestrator for WinFix AI (Phase 11).

Coordinates allowlisted, user-confirmed Bluetooth repair operations:
1. restart_bluetooth_service (restart Windows Bluetooth Support Service 'bthserv')

Enforces strict before-state capture, cryptographic SHA-256 confirmation token binding,
after-state deterministic verification, and SQLite audit logging.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from agent.bluetooth_diagnostics import BluetoothDiagnosis
from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
from windows.bluetooth_repairs import BLUETOOTH_SERVICE_NAME

logger = logging.getLogger(__name__)


@dataclass
class BluetoothRepairProposal:
    """Structured proposal for a Bluetooth repair operation requiring user confirmation."""

    tool_name: str = "restart_bluetooth_service"
    arguments: Dict[str, Any] = field(default_factory=dict)
    service_name: str = BLUETOOTH_SERVICE_NAME
    display_name: str = "Bluetooth Support Service"
    reason: str = "Restart the Windows Bluetooth Support Service to restore radio and device communications."
    expected_effect: str = "Stop and restart 'bthserv', restoring RUNNING state and reinitializing Bluetooth stack."
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
class BluetoothRepairExecutionResult:
    """Structured outcome of an executed Bluetooth repair with verification details."""

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


class BluetoothRepairsOrchestrator:
    """Coordinates allowlisted Bluetooth repairs with explicit user confirmation and verification."""

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
        diagnosis: BluetoothDiagnosis,
        session_id: Optional[str] = None,
    ) -> Optional[BluetoothRepairProposal]:
        """Construct an exact confirmation-bound repair proposal if an approved Bluetooth repair is available."""
        if not diagnosis.repair_available or diagnosis.proposed_tool != "restart_bluetooth_service":
            return None

        return BluetoothRepairProposal(
            tool_name="restart_bluetooth_service",
            arguments={},
            service_name=BLUETOOTH_SERVICE_NAME,
            display_name="Bluetooth Support Service",
            reason="Bluetooth service is stopped or inactive. Restarting 'bthserv' will reinitialize the radio stack.",
            expected_effect="Restart 'bthserv' and verify it achieves RUNNING state.",
            risk="MEDIUM",
            requires_admin=True,
            verification_tool="get_service_status",
        )

    def execute_confirmed_repair(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        confirmation_token: str,
        session_id: Optional[str] = None,
    ) -> BluetoothRepairExecutionResult:
        """Execute an approved Bluetooth repair after validating the confirmation token."""
        # 1. Token validation
        if not self.validate_confirmation_token(confirmation_token, tool_name, arguments, session_id):
            logger.warning("Rejected unconfirmed or tampered Bluetooth repair token for %s", tool_name)
            return BluetoothRepairExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="Execution blocked: Confirmation token is invalid or does not match parameters/session.",
            )

        # 2. Allowlist tool check
        allowed_tools = {"restart_bluetooth_service"}
        if tool_name not in allowed_tools:
            return BluetoothRepairExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                confirmed=True,
                repair_success=False,
                verification_status="blocked",
                explanation=f"Execution blocked: Tool '{tool_name}' is not an approved Bluetooth repair tool.",
            )

        # 3. Capture Before-State
        before_res = self.safety_engine.execute(
            tool_name="get_service_status",
            arguments={"service_name": BLUETOOTH_SERVICE_NAME},
            session_id=session_id,
        )
        before_state = before_res.get("data") if before_res["success"] else None

        # 4. Execute Repair Tool
        repair_res = self.safety_engine.execute(
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
        )
        repair_success = repair_res.get("success", False)
        repair_output = repair_res.get("data")

        # 5. Capture After-State (Verification)
        after_res = self.safety_engine.execute(
            tool_name="get_service_status",
            arguments={"service_name": BLUETOOTH_SERVICE_NAME},
            session_id=session_id,
        )
        after_state = after_res.get("data") if after_res["success"] else None

        # 6. Evaluate Verification Status
        verification_status = "not_verified"
        explanation = ""

        if not repair_success:
            err = repair_res.get("error", {})
            verification_status = "failed"
            explanation = f"Bluetooth repair '{tool_name}' failed: {err.get('message', 'Unknown error')}."
        elif after_state:
            curr_status = after_state.get("status", "UNKNOWN")
            if curr_status == "RUNNING":
                verification_status = "verified"
                explanation = "Bluetooth Support Service restarted successfully and verified RUNNING."
            else:
                verification_status = "not_verified"
                explanation = f"Bluetooth Support Service restart executed but status is {curr_status}."
        else:
            verification_status = "not_verified"
            explanation = "Unable to query Bluetooth service status following repair."

        # 7. Record audit log in SQLite repository
        try:
            if session_id:
                self.solution_repo.create(
                    session_id=session_id,
                    proposed_repair=f"{tool_name} ({BLUETOOTH_SERVICE_NAME})",
                    repair_executed=True,
                    verified_status=verification_status,
                    verification_notes=explanation,
                )
        except Exception as audit_exc:
            logger.error("Failed to audit Bluetooth repair in database: %s", audit_exc)

        return BluetoothRepairExecutionResult(
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
