"""WinFix AI — AI Quality & Diagnostic Evaluation Models (Phase 34).

Defines strongly typed immutable evaluation scenarios, expected outcomes,
metric models, and evaluation run reports for diagnostic intelligence benchmarking.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from agent.domain_models import TroubleshootingDomain


class EvaluationOutcome(str, Enum):
    """Deterministic evaluation outcome for a scenario or test assertion."""

    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class EvaluationScenario:
    """Deterministic test case for diagnostic intelligence evaluation."""

    scenario_id: str
    domain: TroubleshootingDomain
    symptoms: str
    initial_evidence: List[Dict[str, Any]] = field(default_factory=list)
    expected_domain: TroubleshootingDomain = TroubleshootingDomain.UNKNOWN
    expected_hypotheses: List[str] = field(default_factory=list)
    contradictory_evidence: List[Dict[str, Any]] = field(default_factory=list)
    expected_safe_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    expected_resolution_state: str = "RESOLVED"
    severity: str = "NORMAL"
    confidence_expectation: float = 0.8
    multimodal_inputs: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "domain": self.domain.value if isinstance(self.domain, Enum) else str(self.domain),
            "symptoms": self.symptoms,
            "initial_evidence": list(self.initial_evidence),
            "expected_domain": self.expected_domain.value if isinstance(self.expected_domain, Enum) else str(self.expected_domain),
            "expected_hypotheses": list(self.expected_hypotheses),
            "contradictory_evidence": list(self.contradictory_evidence),
            "expected_safe_tools": list(self.expected_safe_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "expected_resolution_state": self.expected_resolution_state,
            "severity": self.severity,
            "confidence_expectation": self.confidence_expectation,
            "multimodal_inputs": dict(self.multimodal_inputs),
            "description": self.description,
        }


@dataclass(frozen=True)
class ScenarioEvaluationResult:
    """Individual scenario evaluation result with granular diagnostic quality scores."""

    scenario_id: str
    domain: TroubleshootingDomain
    outcome: EvaluationOutcome
    domain_matched: bool
    hypotheses_grounded: bool
    unregistered_tools_count: int
    forbidden_tools_count: int
    contradiction_detected: bool
    hallucination_detected: bool
    details: str = ""
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "domain": self.domain.value if isinstance(self.domain, Enum) else str(self.domain),
            "outcome": self.outcome.value,
            "domain_matched": self.domain_matched,
            "hypotheses_grounded": self.hypotheses_grounded,
            "unregistered_tools_count": self.unregistered_tools_count,
            "forbidden_tools_count": self.forbidden_tools_count,
            "contradiction_detected": self.contradiction_detected,
            "hallucination_detected": self.hallucination_detected,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class EvaluationSummary:
    """High-level metrics across all evaluated troubleshooting scenarios."""

    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    partial_scenarios: int
    diagnostic_accuracy_rate: float
    evidence_grounding_rate: float
    contradiction_detection_rate: float
    unsupported_hypothesis_rate: float
    tool_recommendation_accuracy_rate: float
    unregistered_tool_rate: float
    forbidden_tool_rate: float
    hallucination_rate: float
    multimodal_consistency_rate: float
    fallback_success_rate: float
    tutor_compliance_rate: float
    autopilot_safety_rate: float
    knowledge_retrieval_rate: float
    determinism_rate: float
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
