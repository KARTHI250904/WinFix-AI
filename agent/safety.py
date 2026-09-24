"""Safety Validation and Execution Engine for WinFix AI.

Enforces the core rule: LLM != Windows Shell.
Evaluates risk levels (SAFE, MEDIUM, HIGH), validates arguments strictly against
tool schemas, prevents command injection, and audits all tool executions.
"""

from dataclasses import dataclass
import json
import logging
import time
from typing import Any, Dict, Optional

from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, default_tool_registry
from database.repositories.tool_executions import ToolExecutionRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyDecision:
    """Represents a formal policy evaluation decision for a requested tool execution."""

    allowed: bool
    requires_confirmation: bool
    blocked: bool
    risk: str
    reason: str
    validated_arguments: Dict[str, Any]


class SafetyEngine:
    """Enforces safety policies, argument validation, and controlled execution."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        execution_repo: Optional[ToolExecutionRepository] = None,
    ) -> None:
        self.registry = registry or default_tool_registry
        self.execution_repo = execution_repo

    def evaluate(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        user_confirmed: bool = False,
    ) -> SafetyDecision:
        """Evaluate a tool invocation request against safety rules and argument schemas."""
        raw_args = arguments or {}

        # 1. Reject unknown or unregistered tools (Fail Closed)
        tool = self.registry.get(tool_name)
        if not tool:
            return SafetyDecision(
                allowed=False,
                requires_confirmation=False,
                blocked=True,
                risk=RiskLevel.HIGH.value,
                reason=f"Tool '{tool_name}' is not registered in the approved ToolRegistry.",
                validated_arguments={},
            )

        # 2. Strict argument validation
        val_success, val_args, err_reason = self._validate_arguments(tool, raw_args)
        if not val_success:
            return SafetyDecision(
                allowed=False,
                requires_confirmation=False,
                blocked=True,
                risk=tool.risk.value,
                reason=f"Argument validation failed: {err_reason}",
                validated_arguments={},
            )

        # 3. Policy evaluation based on RiskLevel
        if tool.risk == RiskLevel.HIGH:
            return SafetyDecision(
                allowed=False,
                requires_confirmation=False,
                blocked=True,
                risk=RiskLevel.HIGH.value,
                reason="HIGH risk operations are strictly blocked by safety policy.",
                validated_arguments=val_args,
            )

        if tool.risk == RiskLevel.MEDIUM:
            if user_confirmed:
                return SafetyDecision(
                    allowed=True,
                    requires_confirmation=False,
                    blocked=False,
                    risk=RiskLevel.MEDIUM.value,
                    reason="MEDIUM risk operation confirmed by user.",
                    validated_arguments=val_args,
                )
            return SafetyDecision(
                allowed=False,
                requires_confirmation=True,
                blocked=False,
                risk=RiskLevel.MEDIUM.value,
                reason="MEDIUM risk operation requires explicit user confirmation.",
                validated_arguments=val_args,
            )

        # SAFE tools are allowed automatically
        return SafetyDecision(
            allowed=True,
            requires_confirmation=False,
            blocked=False,
            risk=RiskLevel.SAFE.value,
            reason="Approved SAFE read-only diagnostic tool.",
            validated_arguments=val_args,
        )

    def _validate_arguments(
        self, tool: ToolDefinition, raw_args: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any], Optional[str]]:
        """Validate input arguments against the tool's parameter specification."""
        validated: Dict[str, Any] = {}

        # Check for unexpected arguments (Strict Whitelisting)
        for key in raw_args:
            if key not in tool.parameters:
                return (
                    False,
                    {},
                    f"Unexpected argument '{key}' not accepted by tool '{tool.name}'.",
                )

        # Validate specified parameters
        for p_name, p_spec in tool.parameters.items():
            if p_name in raw_args:
                val = raw_args[p_name]
            else:
                val = p_spec.default

            valid, err = p_spec.validate(val)
            if not valid:
                return False, {}, err

            if val is not None:
                validated[p_name] = val

        return True, validated, None

    def execute(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """Validate, authorize, execute the registered tool handler, and audit log the outcome."""
        start_time = time.time()
        decision = self.evaluate(tool_name, arguments, user_confirmed=user_confirmed)

        tool = self.registry.get(tool_name)
        domain = tool.domain if tool else "unknown"
        risk_str = tool.risk.value if tool else RiskLevel.HIGH.value
        req_admin = tool.requires_admin if tool else False

        # If not allowed by safety policy, fail closed immediately
        if not decision.allowed:
            duration_ms = int((time.time() - start_time) * 1000)
            err_dict = {
                "code": "SAFETY_BLOCKED" if decision.blocked else "CONFIRMATION_REQUIRED",
                "message": decision.reason,
            }
            logger.warning("Tool execution blocked for %s: %s", tool_name, decision.reason)

            # Audit log safety rejection if session_id is provided
            self._log_audit(
                session_id=session_id,
                tool_name=tool_name,
                risk_level=risk_str,
                requires_admin=req_admin,
                success=False,
                duration_ms=duration_ms,
                error_message=decision.reason,
                result_json=None,
            )

            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "risk": risk_str,
                "data": None,
                "error": err_dict,
                "duration_ms": duration_ms,
                "safety": {
                    "allowed": False,
                    "requires_confirmation": decision.requires_confirmation,
                    "blocked": decision.blocked,
                    "reason": decision.reason,
                },
            }

        # Handler existence check (Fail closed)
        if not tool or tool.handler is None or not callable(tool.handler):
            duration_ms = int((time.time() - start_time) * 1000)
            reason = f"No executable handler registered for tool '{tool_name}'."
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "risk": risk_str,
                "data": None,
                "error": {"code": "MISSING_HANDLER", "message": reason},
                "duration_ms": duration_ms,
                "safety": {"allowed": False, "reason": reason},
            }

        # Safe execution of registered Python handler
        try:
            handler_result = tool.handler(**decision.validated_arguments)
            duration_ms = int((time.time() - start_time) * 1000)

            if isinstance(handler_result, dict):
                success = bool(handler_result.get("success", True))
                data = handler_result["data"] if "data" in handler_result else handler_result
                err = handler_result.get("error")
            else:
                success = True
                data = handler_result
                err = None

            # Audit log execution
            result_str = json.dumps(data, default=str) if data is not None else None
            err_str = json.dumps(err, default=str) if err is not None else None

            self._log_audit(
                session_id=session_id,
                tool_name=tool_name,
                risk_level=risk_str,
                requires_admin=req_admin,
                success=success,
                duration_ms=duration_ms,
                error_message=err_str,
                result_json=result_str,
            )

            return {
                "success": success,
                "tool": tool_name,
                "domain": domain,
                "risk": risk_str,
                "data": data,
                "error": err,
                "duration_ms": duration_ms,
                "safety": {
                    "allowed": True,
                    "requires_confirmation": False,
                    "blocked": False,
                    "reason": decision.reason,
                },
            }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error("Handler execution exception in %s: %s", tool_name, exc)

            self._log_audit(
                session_id=session_id,
                tool_name=tool_name,
                risk_level=risk_str,
                requires_admin=req_admin,
                success=False,
                duration_ms=duration_ms,
                error_message=str(exc),
                result_json=None,
            )

            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "risk": risk_str,
                "data": None,
                "error": {"code": "HANDLER_EXCEPTION", "message": str(exc)},
                "duration_ms": duration_ms,
                "safety": {"allowed": True, "reason": decision.reason},
            }

    def _log_audit(
        self,
        session_id: Optional[str],
        tool_name: str,
        risk_level: str,
        requires_admin: bool,
        success: bool,
        duration_ms: int,
        error_message: Optional[str],
        result_json: Optional[str],
    ) -> None:
        """Safely record audit log to SQLite if a session repository is configured."""
        if not session_id or not self.execution_repo:
            return
        try:
            self.execution_repo.create(
                session_id=session_id,
                tool_name=tool_name,
                risk_level=risk_level,
                requires_admin=requires_admin,
                success=success,
                duration_ms=duration_ms,
                error_message=error_message,
                result_json=result_json,
            )
        except Exception as audit_err:
            logger.error("Failed to write audit log for %s: %s", tool_name, audit_err)


# Default shared safety engine instance
default_safety_engine = SafetyEngine()
