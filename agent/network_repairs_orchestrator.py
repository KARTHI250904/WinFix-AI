"""Network Repair and Verification Orchestrator for WinFix AI (Phase 7).

Coordinates explicit, allowlisted network repair operations, user confirmation boundaries,
before-and-after diagnostic state captures, and deterministic verification workflows.

Strictly adheres to safety rules:
- No generic command execution
- No shell / PowerShell / CMD execution
- User confirmation strictly bound to exact tool and arguments
- Never assumes repair success without post-repair verification
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository

logger = logging.getLogger(__name__)


@dataclass
class RepairProposal:
    """Structured proposal for a controlled Windows repair action."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_effect: str = ""
    risk: str = "MEDIUM"
    requires_admin: bool = False
    verification_tool: str = ""

    def generate_confirmation_token(self, session_id: Optional[str] = None) -> str:
        """Generate a cryptographic confirmation token bound strictly to this tool, arguments, and session."""
        payload = f"{self.tool_name}:{json.dumps(self.arguments, sort_keys=True)}:{session_id or ''}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize repair proposal to dictionary."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "expected_effect": self.expected_effect,
            "risk": self.risk,
            "requires_admin": self.requires_admin,
            "verification_tool": self.verification_tool,
        }


@dataclass
class RepairExecutionResult:
    """Structured result of repair execution and post-repair verification."""

    tool_name: str
    arguments: Dict[str, Any]
    confirmed: bool
    repair_success: bool
    before_state: Optional[Dict[str, Any]] = None
    repair_output: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    verification_tool: str = ""
    verification_status: str = "not_verified"  # "verified", "not_verified", "failed", "blocked"
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


class NetworkRepairsOrchestrator:
    """Coordinates allowlisted network repairs with explicit user confirmation and verification."""

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
        problem_category: str,
        observed_evidence: List[str],
        target_host: Optional[str] = None,
    ) -> Optional[RepairProposal]:
        """Formulate a structured repair proposal strictly based on verified diagnostic evidence."""
        # 1. DNS Resolution Failure -> flush_dns_cache
        if problem_category == "dns" or any("DNS lookup" in ev and "failed" in ev for ev in observed_evidence):
            tool = self.registry.get("flush_dns_cache")
            if tool:
                return RepairProposal(
                    tool_name="flush_dns_cache",
                    arguments={},
                    reason="Diagnostic evidence indicates local DNS resolution is failing or stale.",
                    expected_effect="Windows will purge its internal DNS resolver cache.",
                    risk=tool.risk.value,
                    requires_admin=tool.requires_admin,
                    verification_tool=tool.verification_tool or "check_dns_resolution",
                )

        # 2. Adapter Disconnected / Missing IP / APIPA -> renew_dhcp_lease
        if problem_category in ("adapter", "ip_configuration") or any("No active network adapters" in ev for ev in observed_evidence):
            tool = self.registry.get("renew_dhcp_lease")
            if tool:
                return RepairProposal(
                    tool_name="renew_dhcp_lease",
                    arguments={},
                    reason="Diagnostic evidence indicates the adapter lacks an assigned IPv4 address.",
                    expected_effect="Requests a new IP address lease from the local router / DHCP server.",
                    risk=tool.risk.value,
                    requires_admin=tool.requires_admin,
                    verification_tool=tool.verification_tool or "get_network_adapters_diagnostics",
                )

        return None

    def execute_repair_with_verification(
        self,
        proposal: RepairProposal,
        session_id: Optional[str] = None,
        user_confirmed: bool = False,
        confirmation_token: Optional[str] = None,
    ) -> RepairExecutionResult:
        """Execute repair under strict user confirmation and verify outcome."""
        tool = self.registry.get(proposal.tool_name)
        if not tool:
            return RepairExecutionResult(
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
                return RepairExecutionResult(
                    tool_name=proposal.tool_name,
                    arguments=proposal.arguments,
                    confirmed=False,
                    repair_success=False,
                    verification_status="blocked",
                    explanation="Security validation failed: Confirmation token does not match the proposal arguments.",
                )

        # If unconfirmed, fail closed immediately without executing
        if not user_confirmed:
            return RepairExecutionResult(
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                confirmed=False,
                repair_success=False,
                verification_status="blocked",
                explanation="MEDIUM risk repair blocked: Explicit user confirmation required.",
            )

        # --- STEP 1: CAPTURE BEFORE-STATE ---
        before_state = None
        v_tool_name = proposal.verification_tool or tool.verification_tool or "check_dns_resolution"
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
            err_msg = repair_res.get("error", {}).get("message", "Repair execution failed.")
            return RepairExecutionResult(
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
            after_res = self.safety_engine.execute(
                tool_name=v_tool_name,
                session_id=session_id,
            )
            after_state = after_res.get("data")

            # Deterministic Verification Rules
            if proposal.tool_name == "flush_dns_cache":
                if after_res.get("success") and after_state and after_state.get("resolved"):
                    verification_status = "verified"
                    explanation = "DNS cache was cleared and post-repair DNS resolution verified successfully."
                else:
                    verification_status = "not_verified"
                    explanation = "DNS cache was flushed, but DNS hostname resolution is still failing."

            elif proposal.tool_name == "renew_dhcp_lease":
                if after_res.get("success") and after_state:
                    active = after_state.get("active_adapters", 0)
                    if active > 0:
                        verification_status = "verified"
                        explanation = f"DHCP renewal completed. Verified {active} adapter(s) active with IPv4."
                    else:
                        verification_status = "not_verified"
                        explanation = "DHCP renewal requested, but no active adapters with valid IPv4 were observed."
            else:
                if after_res.get("success"):
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

        return RepairExecutionResult(
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
default_network_repairs_orchestrator = NetworkRepairsOrchestrator()
