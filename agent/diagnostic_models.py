"""WinFix AI — Diagnostic Intelligence & Hypothesis Models (Phase 27).

Defines strongly-typed diagnostic hypotheses, plan structures, loop limits,
and structured diagnostic response containers separating Observation, Interpretation,
Hypothesis, and Recommendation.
Strictly adheres to: Diagnosis != Windows Command and Hypothesis != Windows Command.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("winfix.DIAGNOSTIC_MODELS")


class HypothesisStatus(str, Enum):
    """Validation status of a diagnostic hypothesis."""

    POSSIBLE = "POSSIBLE"
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"
    VERIFIED = "VERIFIED"       # Allowed ONLY via deterministic tool verification


@dataclass(frozen=True)
class DiagnosticHypothesis:
    """Strongly-typed diagnostic hypothesis explaining potential root causes."""

    hypothesis_id: str
    category: str
    statement: str
    supporting_evidence_ids: List[str] = field(default_factory=list)
    contradicting_evidence_ids: List[str] = field(default_factory=list)
    affected_component: str = ""
    severity: str = "NORMAL"
    status: HypothesisStatus = HypothesisStatus.POSSIBLE
    recommended_tools: List[str] = field(default_factory=list)
    explanation: str = ""
    uncertainty_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert hypothesis to dictionary."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "category": self.category,
            "statement": self.statement,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "affected_component": self.affected_component,
            "severity": self.severity,
            "status": self.status.value,
            "recommended_tools": list(self.recommended_tools),
            "explanation": self.explanation,
            "uncertainty_notes": self.uncertainty_notes,
        }


@dataclass
class DiagnosticPlanStep:
    """A single deterministic diagnostic step."""

    step_id: int
    tool_name: str
    purpose: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    expected_evidence: str = ""
    dependencies: List[int] = field(default_factory=list)
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary."""
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "purpose": self.purpose,
            "arguments": self.arguments,
            "expected_evidence": self.expected_evidence,
            "dependencies": self.dependencies,
            "status": self.status,
            "result": self.result,
        }


@dataclass
class DiagnosticPlan:
    """Deterministic, bounded sequence of diagnostic tool executions."""

    plan_id: str
    session_id: str
    problem_category: str
    steps: List[DiagnosticPlanStep] = field(default_factory=list)
    max_steps: int = 5
    current_step_index: int = 0
    status: str = "READY"  # READY, IN_PROGRESS, COMPLETED, FAILED, CANCELLED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate_plan_limits(self) -> bool:
        """Enforce maximum 5 steps and maximum 1 execution per tool (loop protection)."""
        if len(self.steps) > self.max_steps:
            return False

        tool_names = [step.tool_name for step in self.steps]
        # Max 1 execution per unique tool within a single plan
        if len(tool_names) != len(set(tool_names)):
            return False

        return True

    def get_next_pending_step(self) -> Optional[DiagnosticPlanStep]:
        """Retrieve the next executable step."""
        for step in self.steps:
            if step.status == "PENDING":
                return step
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize plan to dictionary."""
        return {
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "problem_category": self.problem_category,
            "steps": [s.to_dict() for s in self.steps],
            "max_steps": self.max_steps,
            "current_step_index": self.current_step_index,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class DiagnosticResponse:
    """Structured response container separating Observation, Interpretation, Hypothesis, and Recommendation."""

    summary: str = ""
    observations: List[str] = field(default_factory=list)      # Factual raw observations
    interpretations: List[str] = field(default_factory=list)   # Deductions / implications
    hypotheses: List[DiagnosticHypothesis] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list) # IDs of evidence
    recommended_tools: List[str] = field(default_factory=list)  # Validated tool names
    diagnostic_plan: Optional[DiagnosticPlan] = None
    uncertainty: List[str] = field(default_factory=list)       # Missing/unverified aspects
    tutor_explanation: Optional[str] = None
    confidence: float = 0.8
    is_degraded: bool = False
    raw_json: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize response to standard dictionary."""
        return {
            "summary": self.summary,
            "observations": list(self.observations),
            "interpretations": list(self.interpretations),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "evidence_references": list(self.evidence_references),
            "recommended_tools": list(self.recommended_tools),
            "diagnostic_plan": self.diagnostic_plan.to_dict() if self.diagnostic_plan else None,
            "uncertainty": list(self.uncertainty),
            "tutor_explanation": self.tutor_explanation,
            "confidence": self.confidence,
            "is_degraded": self.is_degraded,
        }
