"""WinFix AI — Production Recovery & Resumable Workflow Models (Phase 31).

Defines strongly-typed models for workflow checkpoints, recovery events,
resumption decisions, execution records, and recovery states.
Strictly adheres to:
  Execution Success != Verification Success
  Never Assume Previous Repair Executed Successfully
  Revalidate Current Windows State Before Resuming
  Repair Replay Strictly Prohibited
  Zero Prohibited AST Calls
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from agent.domain_models import FailureCategory, TroubleshootingDomain
from agent.workflow_models import WorkflowStatus

logger = logging.getLogger("winfix.RECOVERY_MODELS")


class RecoveryState(str, Enum):
    """Lifecycle states of the recovery manager."""

    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"
    REVALIDATING = "REVALIDATING"
    RESUMABLE = "RESUMABLE"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    RESUMED = "RESUMED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    UNRESOLVED = "UNRESOLVED"
    COMPLETED = "COMPLETED"


class RecoveryEventType(str, Enum):
    """Standardized operational recovery event types."""

    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    CHECKPOINT_UPDATED = "CHECKPOINT_UPDATED"
    WORKFLOW_INTERRUPTED = "WORKFLOW_INTERRUPTED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    STATE_REVALIDATED = "STATE_REVALIDATED"
    EVIDENCE_REVALIDATED = "EVIDENCE_REVALIDATED"
    AUTHORIZATION_INVALIDATED = "AUTHORIZATION_INVALIDATED"
    REPAIR_REPLAY_BLOCKED = "REPAIR_REPLAY_BLOCKED"
    WORKFLOW_RESUMED = "WORKFLOW_RESUMED"
    WORKFLOW_CANCELLED = "WORKFLOW_CANCELLED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"


class ResumeAction(str, Enum):
    """Authoritative actions determined by the ResumeEngine."""

    RESUME = "RESUME"
    REVALIDATE = "REVALIDATE"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    CANCEL = "CANCEL"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Checkpoint:
    """Sanitized, persistent state record of an active troubleshooting workflow."""

    checkpoint_id: str
    session_id: str
    workflow_id: str
    step_id: int
    workflow_state: str  # WorkflowStatus value
    current_step_index: int
    domain: str  # TroubleshootingDomain value
    evidence_references: List[str] = field(default_factory=list)
    hypothesis_references: List[str] = field(default_factory=list)
    diagnostic_decisions: List[Dict[str, Any]] = field(default_factory=list)
    repair_candidate: Optional[Dict[str, Any]] = None
    authorization_state: Optional[Dict[str, Any]] = None
    execution_state: Optional[Dict[str, Any]] = None
    verification_state: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "1.0"

    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        """Check whether the checkpoint exceeds the allowable resumption TTL."""
        try:
            ts = datetime.fromisoformat(self.updated_at)
            now = datetime.now(timezone.utc)
            return (now - ts).total_seconds() > max_age_seconds
        except Exception:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "workflow_state": self.workflow_state,
            "current_step_index": self.current_step_index,
            "domain": self.domain,
            "evidence_references": list(self.evidence_references),
            "hypothesis_references": list(self.hypothesis_references),
            "diagnostic_decisions": list(self.diagnostic_decisions),
            "repair_candidate": self.repair_candidate,
            "authorization_state": self.authorization_state,
            "execution_state": self.execution_state,
            "verification_state": self.verification_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            session_id=data["session_id"],
            workflow_id=data["workflow_id"],
            step_id=data.get("step_id", 0),
            workflow_state=data.get("workflow_state", "CREATED"),
            current_step_index=data.get("current_step_index", 0),
            domain=data.get("domain", "UNKNOWN"),
            evidence_references=data.get("evidence_references", []),
            hypothesis_references=data.get("hypothesis_references", []),
            diagnostic_decisions=data.get("diagnostic_decisions", []),
            repair_candidate=data.get("repair_candidate"),
            authorization_state=data.get("authorization_state"),
            execution_state=data.get("execution_state"),
            verification_state=data.get("verification_state"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            schema_version=data.get("schema_version", "1.0"),
        )


@dataclass(frozen=True)
class ExecutionRecord:
    """Immutable audit record of a discrete tool execution attempt."""

    execution_id: str
    session_id: str
    workflow_id: str
    step_id: int
    tool_name: str
    argument_hash: str
    authorization_hash: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    execution_status: str = "STARTED"  # STARTED, SUCCEEDED, FAILED, TIMEOUT, UNKNOWN
    verification_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "argument_hash": self.argument_hash,
            "authorization_hash": self.authorization_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRecord":
        return cls(
            execution_id=data["execution_id"],
            session_id=data["session_id"],
            workflow_id=data["workflow_id"],
            step_id=data.get("step_id", 0),
            tool_name=data["tool_name"],
            argument_hash=data["argument_hash"],
            authorization_hash=data.get("authorization_hash"),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            completed_at=data.get("completed_at"),
            execution_status=data.get("execution_status", "STARTED"),
            verification_status=data.get("verification_status"),
        )


@dataclass(frozen=True)
class RecoveryEvent:
    """Sanitized operational telemetry record of recovery and resumption actions."""

    event_id: str
    session_id: str
    workflow_id: str
    event_type: RecoveryEventType
    state_before: str
    state_after: str
    tool_id: Optional[str] = None
    details: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "event_type": self.event_type.value,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "tool_id": self.tool_id,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ResumeDecision:
    """Authoritative outcome determining how an interrupted workflow must proceed."""

    decision_id: str
    action: ResumeAction
    rationale: str
    safe_step_index: int = 0
    target_tool: Optional[str] = None
    requires_reauthorization: bool = False
    revalidation_evidence: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action": self.action.value,
            "rationale": self.rationale,
            "safe_step_index": self.safe_step_index,
            "target_tool": self.target_tool,
            "requires_reauthorization": self.requires_reauthorization,
            "revalidation_evidence": self.revalidation_evidence,
            "timestamp": self.timestamp,
        }


@dataclass
class RecoveryResult:
    """Structured result of a recovery operation."""

    recovery_id: str
    session_id: str
    workflow_id: str
    state: RecoveryState
    decision: ResumeDecision
    explanation: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "state": self.state.value,
            "decision": self.decision.to_dict(),
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }
