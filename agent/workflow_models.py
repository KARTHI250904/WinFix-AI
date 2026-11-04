"""WinFix AI — Intelligent Troubleshooting Workflow Models (Phase 28).

Defines strongly-typed workflow data structures, state machines, repair candidates,
and verification containers for guided resolution.
Strictly adheres to:
  Diagnosis != Repair Authorization
  Repair Candidate != Repair Authorization
  Repair Execution != Success
  Deterministic Verification != LLM Hallucination
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("winfix.WORKFLOW_MODELS")


class WorkflowStatus(str, Enum):
    """Lifecycle statuses for a troubleshooting workflow."""

    CREATED = "CREATED"
    DIAGNOSING = "DIAGNOSING"
    VERIFY_PRECONDITION = "VERIFY_PRECONDITION"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    REPAIRING = "REPAIRING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"


class StepType(str, Enum):
    """Controlled, allowlisted workflow step types."""

    OBSERVE = "OBSERVE"
    DIAGNOSE = "DIAGNOSE"
    VERIFY_PRECONDITION = "VERIFY_PRECONDITION"
    REQUEST_CONFIRMATION = "REQUEST_CONFIRMATION"
    REPAIR = "REPAIR"
    VERIFY_REPAIR = "VERIFY_REPAIR"
    EXPLAIN = "EXPLAIN"
    COMPLETE = "COMPLETE"


class ResolutionStatus(str, Enum):
    """Deterministic resolution outcomes."""

    RESOLVED = "RESOLVED"
    NOT_RESOLVED = "NOT_RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    INCONCLUSIVE = "INCONCLUSIVE"


# Valid state transitions enforced by the state machine
VALID_WORKFLOW_TRANSITIONS: Dict[WorkflowStatus, List[WorkflowStatus]] = {
    WorkflowStatus.CREATED: [
        WorkflowStatus.DIAGNOSING,
        WorkflowStatus.VERIFY_PRECONDITION,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.FAILED,
        WorkflowStatus.UNRESOLVED,
        WorkflowStatus.PAUSED,
    ],
    WorkflowStatus.DIAGNOSING: [
        WorkflowStatus.VERIFY_PRECONDITION,
        WorkflowStatus.WAITING_FOR_CONFIRMATION,
        WorkflowStatus.UNRESOLVED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.PAUSED,
    ],
    WorkflowStatus.VERIFY_PRECONDITION: [
        WorkflowStatus.WAITING_FOR_CONFIRMATION,
        WorkflowStatus.REPAIRING,
        WorkflowStatus.FAILED,
        WorkflowStatus.UNRESOLVED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.PAUSED,
    ],
    WorkflowStatus.WAITING_FOR_CONFIRMATION: [
        WorkflowStatus.REPAIRING,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.PAUSED,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.REPAIRING: [
        WorkflowStatus.VERIFYING,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    ],
    WorkflowStatus.VERIFYING: [
        WorkflowStatus.RESOLVED,
        WorkflowStatus.PARTIALLY_RESOLVED,
        WorkflowStatus.UNRESOLVED,
        WorkflowStatus.DIAGNOSING,  # safe fallback for alternative branch if steps remain
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    ],
    WorkflowStatus.PAUSED: [
        WorkflowStatus.DIAGNOSING,
        WorkflowStatus.VERIFY_PRECONDITION,
        WorkflowStatus.WAITING_FOR_CONFIRMATION,
        WorkflowStatus.CANCELLED,
    ],
    # Terminal states have no outbound transitions
    WorkflowStatus.RESOLVED: [],
    WorkflowStatus.UNRESOLVED: [],
    WorkflowStatus.PARTIALLY_RESOLVED: [],
    WorkflowStatus.FAILED: [],
    WorkflowStatus.CANCELLED: [],
    WorkflowStatus.EXPIRED: [],
}


@dataclass
class RepairCandidate:
    """Strongly-typed repair proposal requiring validation and authorization."""

    candidate_id: str
    diagnosis_id: str
    tool_name: str
    purpose: str
    supporting_evidence: List[str] = field(default_factory=list)
    preconditions: Dict[str, Any] = field(default_factory=dict)
    expected_effect: str = ""
    verification_method: str = ""  # The diagnostic tool to run after repair
    risk_level: str = "MEDIUM"
    authorization_required: bool = True
    arguments: Dict[str, Any] = field(default_factory=dict)
    session_id: str = "default_session"
    workflow_id: str = ""

    def generate_confirmation_token(self) -> str:
        """Generate a cryptographic token bound strictly to session, workflow, tool, and arguments."""
        payload = f"{self.session_id}:{self.workflow_id}:{self.tool_name}:{json.dumps(self.arguments, sort_keys=True)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert repair candidate to dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "diagnosis_id": self.diagnosis_id,
            "tool_name": self.tool_name,
            "purpose": self.purpose,
            "supporting_evidence": list(self.supporting_evidence),
            "preconditions": dict(self.preconditions),
            "expected_effect": self.expected_effect,
            "verification_method": self.verification_method,
            "risk_level": self.risk_level,
            "authorization_required": self.authorization_required,
            "arguments": dict(self.arguments),
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
        }


@dataclass
class WorkflowStep:
    """A discrete, validated step in a troubleshooting workflow."""

    step_id: int
    workflow_id: str
    sequence: int
    step_type: StepType
    purpose: str
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    expected_evidence: str = ""
    preconditions: Dict[str, Any] = field(default_factory=dict)
    authorization_required: bool = False
    verification_required: bool = False
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, CANCELLED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary."""
        return {
            "step_id": self.step_id,
            "workflow_id": self.workflow_id,
            "sequence": self.sequence,
            "step_type": self.step_type.value if isinstance(self.step_type, StepType) else str(self.step_type),
            "purpose": self.purpose,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "expected_evidence": self.expected_evidence,
            "preconditions": dict(self.preconditions),
            "authorization_required": self.authorization_required,
            "verification_required": self.verification_required,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
        }


@dataclass
class TroubleshootingWorkflow:
    """Bounded, deterministic troubleshooting workflow state."""

    workflow_id: str
    session_id: str
    problem_category: str
    title: str
    description: str = ""
    diagnosis_id: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    current_step: int = 0
    max_steps: int = 8
    status: WorkflowStatus = WorkflowStatus.CREATED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cancellation_requested: bool = False
    resolution_status: ResolutionStatus = ResolutionStatus.INCONCLUSIVE
    failure_reason: str = ""
    repair_candidate: Optional[RepairCandidate] = None
    before_evidence: Dict[str, Any] = field(default_factory=dict)
    after_evidence: Dict[str, Any] = field(default_factory=dict)
    executed_repair_tools: List[str] = field(default_factory=list)
    tutor_explanation: str = ""
    audit_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "problem_category": self.problem_category,
            "title": self.title,
            "description": self.description,
            "diagnosis_id": self.diagnosis_id,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "status": self.status.value if isinstance(self.status, WorkflowStatus) else str(self.status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cancellation_requested": self.cancellation_requested,
            "resolution_status": self.resolution_status.value if isinstance(self.resolution_status, ResolutionStatus) else str(self.resolution_status),
            "failure_reason": self.failure_reason,
            "repair_candidate": self.repair_candidate.to_dict() if self.repair_candidate else None,
            "before_evidence": self.before_evidence,
            "after_evidence": self.after_evidence,
            "executed_repair_tools": list(self.executed_repair_tools),
            "tutor_explanation": self.tutor_explanation,
            "audit_events": list(self.audit_events),
        }
