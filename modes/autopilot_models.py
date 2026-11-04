"""WinFix AI — Autopilot Mode Structured Models.

Defines typed structures for Autopilot plans, steps, preconditions, results,
and operational status values. Enforces strict type safety and determinism.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class AutopilotStatus(str, Enum):
    """Operational and lifecycle status of an Autopilot plan or execution."""

    PLANNED = "PLANNED"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    STOPPED = "STOPPED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_TIMEOUT = "VERIFICATION_TIMEOUT"
    CANCELLED = "CANCELLED"


class PreconditionOperator(str, Enum):
    """Allowlisted deterministic precondition comparison operators."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    EXISTS = "exists"


@dataclass
class AutopilotPrecondition:
    """Precondition evaluated against the result of a preceding step."""

    step_sequence: int
    path: str
    operator: str
    expected_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert precondition to serializable dictionary."""
        return {
            "step_sequence": self.step_sequence,
            "path": self.path,
            "operator": self.operator,
            "expected_value": self.expected_value,
        }


@dataclass
class AutopilotStep:
    """A discrete, validated step in an Autopilot plan."""

    step_id: str
    sequence: int
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    purpose: str = ""
    expected_result: str = ""
    risk_level: str = "SAFE"
    requires_confirmation: bool = False
    requires_admin: bool = False
    verification_required: bool = False
    depends_on: Optional[int] = None
    preconditions: List[AutopilotPrecondition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to serializable dictionary."""
        return {
            "step_id": self.step_id,
            "sequence": self.sequence,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "purpose": self.purpose,
            "expected_result": self.expected_result,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "requires_admin": self.requires_admin,
            "verification_required": self.verification_required,
            "depends_on": self.depends_on,
            "preconditions": [p.to_dict() for p in self.preconditions],
        }


@dataclass
class AutopilotStepResult:
    """The outcome of executing an individual Autopilot step."""

    step_id: str
    sequence: int
    tool_name: str
    status: str
    output: Dict[str, Any] = field(default_factory=dict)
    verification_status: Optional[str] = None
    verification_output: Optional[Dict[str, Any]] = None
    duration_ms: int = 0
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert step result to serializable dictionary."""
        return {
            "step_id": self.step_id,
            "sequence": self.sequence,
            "tool_name": self.tool_name,
            "status": self.status,
            "output": self.output,
            "verification_status": self.verification_status,
            "verification_output": self.verification_output,
            "duration_ms": self.duration_ms,
            "explanation": self.explanation,
        }


@dataclass
class AutopilotPlan:
    """A bounded, validated, and hash-bound Autopilot execution plan."""

    plan_id: str
    session_id: str
    goal: str
    steps: List[AutopilotStep]
    plan_hash: str
    status: AutopilotStatus = AutopilotStatus.PLANNED
    created_at: float = field(default_factory=time.time)
    is_authorized: bool = False
    is_executed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to serializable dictionary."""
        return {
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "plan_hash": self.plan_hash,
            "status": self.status.value,
            "created_at": self.created_at,
            "is_authorized": self.is_authorized,
            "is_executed": self.is_executed,
        }


@dataclass
class AutopilotResult:
    """The comprehensive result of an Autopilot run."""

    plan_id: str
    session_id: str
    goal: str
    status: AutopilotStatus
    steps_planned: int
    steps_executed: int
    step_results: List[AutopilotStepResult]
    summary: str
    failed_step_sequence: Optional[int] = None
    stopped_reason: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to serializable dictionary."""
        return {
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status.value,
            "steps_planned": self.steps_planned,
            "steps_executed": self.steps_executed,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "summary": self.summary,
            "failed_step_sequence": self.failed_step_sequence,
            "stopped_reason": self.stopped_reason,
            "duration_seconds": self.duration_seconds,
        }
