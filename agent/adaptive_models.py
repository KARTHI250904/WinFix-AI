"""WinFix AI — Adaptive Diagnostic Models & Resolution Analysis (Phase 30).

Defines strongly typed models for adaptive diagnostic reasoning, evidence evolution,
hypothesis transitions, before/after comparisons, and deterministic resolution analysis.
Strictly adheres to:
  Execution Success != Verification Success
  Hypothesis != Authorization
  Candidate != Authorization
  Evidence != Command Execution
  Deterministic Invariants Enforced
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set
import uuid

from agent.domain_models import FailureCategory, TroubleshootingDomain
from agent.diagnostic_models import HypothesisStatus
from agent.workflow_models import ResolutionStatus

logger = logging.getLogger("winfix.ADAPTIVE_MODELS")


class AdaptiveState(str, Enum):
    """Lifecycle states for adaptive diagnostic sessions."""

    INITIAL = "INITIAL"
    COLLECTING = "COLLECTING"
    EVALUATING = "EVALUATING"
    CONTRADICTED = "CONTRADICTED"
    REASSESSING = "REASSESSING"
    ADAPTING = "ADAPTING"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    REPAIRING = "REPAIRING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EvidenceChangeType(str, Enum):
    """Types of evidence mutations or state changes observed during diagnostic flow."""

    NEW = "NEW"
    MUTATED = "MUTATED"
    CONTRADICTED = "CONTRADICTED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    UNCHANGED = "UNCHANGED"


class ResolutionOutcome(str, Enum):
    """Detailed deterministic resolution outcomes."""

    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    VERIFICATION_SUCCEEDED = "VERIFICATION_SUCCEEDED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    CONTRADICTORY = "CONTRADICTORY"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class EvidenceChange:
    """Represents a discrete change or update in factual telemetry."""

    evidence_id: str
    evidence_type: str
    change_type: EvidenceChangeType
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "change_type": self.change_type.value,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class HypothesisTransition:
    """Captures an adaptive transition of a diagnostic hypothesis."""

    transition_id: str
    hypothesis_id: str
    from_status: HypothesisStatus
    to_status: HypothesisStatus
    triggering_evidence_ids: List[str] = field(default_factory=list)
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "hypothesis_id": self.hypothesis_id,
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "triggering_evidence_ids": list(self.triggering_evidence_ids),
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class DiagnosticDecision:
    """Adaptive action determined by the diagnostic engine."""

    decision_id: str
    action_type: str  # "CONTINUE_PLAN", "ADAPT_HYPOTHESIS", "SWITCH_STRATEGY", "PROPOSE_REPAIR", "ABORT_UNRESOLVED", "VERIFY"
    target_strategy_id: Optional[str] = None
    target_tool_name: Optional[str] = None
    hypothesis_id: Optional[str] = None
    rationale: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action_type": self.action_type,
            "target_strategy_id": self.target_strategy_id,
            "target_tool_name": self.target_tool_name,
            "hypothesis_id": self.hypothesis_id,
            "rationale": self.rationale,
            "evidence_ids": list(self.evidence_ids),
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class BeforeAfterComparison:
    """Deterministic comparison between pre-action and post-action evidence."""

    comparison_id: str
    tool_name: str
    pre_evidence: Dict[str, Any]
    post_evidence: Dict[str, Any]
    metric_deltas: Dict[str, Any] = field(default_factory=dict)
    state_changed: bool = False
    verification_passed: bool = False
    details: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "tool_name": self.tool_name,
            "pre_evidence": self.pre_evidence,
            "post_evidence": self.post_evidence,
            "metric_deltas": self.metric_deltas,
            "state_changed": self.state_changed,
            "verification_passed": self.verification_passed,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class ResolutionAnalysis:
    """Comprehensive, deterministic resolution assessment separating execution from verification."""

    session_id: str
    workflow_id: str
    primary_domain: TroubleshootingDomain
    execution_succeeded: bool
    verification_succeeded: bool
    outcome: ResolutionOutcome
    resolution_status: ResolutionStatus
    failure_category: Optional[FailureCategory] = None
    before_after: Optional[BeforeAfterComparison] = None
    explanation: str = ""
    remaining_symptoms: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "primary_domain": self.primary_domain.value if isinstance(self.primary_domain, TroubleshootingDomain) else str(self.primary_domain),
            "execution_succeeded": self.execution_succeeded,
            "verification_succeeded": self.verification_succeeded,
            "outcome": self.outcome.value,
            "resolution_status": self.resolution_status.value,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "before_after": self.before_after.to_dict() if self.before_after else None,
            "explanation": self.explanation,
            "remaining_symptoms": list(self.remaining_symptoms),
            "created_at": self.created_at,
        }


@dataclass
class AdaptiveSessionContext:
    """Bounded, session-scoped adaptive troubleshooting context."""

    session_id: str
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_state: AdaptiveState = AdaptiveState.INITIAL
    primary_domain: TroubleshootingDomain = TroubleshootingDomain.UNKNOWN
    active_hypothesis_id: Optional[str] = None
    active_strategy_id: Optional[str] = None
    step_count: int = 0
    max_steps: int = 8  # Enforced Phase 28 hard limit
    safe_retry_count: int = 0
    max_safe_retries: int = 1  # Hard limit 1
    medium_retry_count: int = 0
    max_medium_retries: int = 0  # Hard limit 0 (no automatic medium retries)
    hypothesis_transitions: List[HypothesisTransition] = field(default_factory=list)
    decisions: List[DiagnosticDecision] = field(default_factory=list)
    evidence_changes: List[EvidenceChange] = field(default_factory=list)
    executed_tools: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def can_execute_step(self) -> bool:
        """Check if workflow step budget is available."""
        return self.step_count < self.max_steps

    def record_step(self, tool_name: str, is_safe: bool = True) -> bool:
        """Record step execution, enforcing bounds."""
        if not self.can_execute_step():
            self.current_state = AdaptiveState.UNRESOLVED
            return False
        self.step_count += 1
        self.executed_tools.append(tool_name)
        return True

    def record_transition(self, transition: HypothesisTransition) -> None:
        """Record an adaptive hypothesis transition."""
        self.hypothesis_transitions.append(transition)

    def record_decision(self, decision: DiagnosticDecision) -> None:
        """Record an adaptive decision."""
        self.decisions.append(decision)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "current_state": self.current_state.value,
            "primary_domain": self.primary_domain.value,
            "active_hypothesis_id": self.active_hypothesis_id,
            "active_strategy_id": self.active_strategy_id,
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "safe_retry_count": self.safe_retry_count,
            "medium_retry_count": self.medium_retry_count,
            "hypothesis_transitions": [t.to_dict() for t in self.hypothesis_transitions],
            "decisions": [d.to_dict() for d in self.decisions],
            "evidence_changes": [c.to_dict() for c in self.evidence_changes],
            "executed_tools": list(self.executed_tools),
            "created_at": self.created_at,
        }
