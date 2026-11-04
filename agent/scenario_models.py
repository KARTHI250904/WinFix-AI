"""WinFix AI — Troubleshooting Scenario Models (Phase 30).

Defines deterministic scenario specifications, synthetic environmental states,
and scenario execution records for real-world validation.
Strictly adheres to:
  Simulation != Destructive Execution
  Deterministic Invariant Verification
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional

from agent.domain_models import TroubleshootingDomain

logger = logging.getLogger("winfix.SCENARIO_MODELS")


@dataclass(frozen=True)
class ScenarioDefinition:
    """Authoritative specification for a deterministic real-world troubleshooting test scenario."""

    scenario_id: str
    domain: TroubleshootingDomain
    initial_user_symptom: str
    initial_state: Dict[str, Any] = field(default_factory=dict)
    available_evidence: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    stale_evidence: List[Dict[str, Any]] = field(default_factory=list)
    contradictory_evidence: List[Dict[str, Any]] = field(default_factory=list)
    expected_hypotheses: List[str] = field(default_factory=list)
    expected_diagnostic_path: List[str] = field(default_factory=list)
    optional_repair: Optional[str] = None
    expected_verification: str = ""
    expected_final_state: str = "RESOLVED"  # RESOLVED, UNRESOLVED, CONTRADICTED, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "domain": self.domain.value if isinstance(self.domain, TroubleshootingDomain) else str(self.domain),
            "initial_user_symptom": self.initial_user_symptom,
            "initial_state": self.initial_state,
            "available_evidence": self.available_evidence,
            "missing_evidence": self.missing_evidence,
            "stale_evidence": self.stale_evidence,
            "contradictory_evidence": self.contradictory_evidence,
            "expected_hypotheses": self.expected_hypotheses,
            "expected_diagnostic_path": self.expected_diagnostic_path,
            "optional_repair": self.optional_repair,
            "expected_verification": self.expected_verification,
            "expected_final_state": self.expected_final_state,
        }


@dataclass
class ScenarioExecutionResult:
    """Outcome record of executing a troubleshooting scenario."""

    scenario_id: str
    passed: bool
    domain: TroubleshootingDomain
    executed_steps: List[str] = field(default_factory=list)
    hypothesis_transitions: List[Dict[str, Any]] = field(default_factory=list)
    final_state: str = "INITIAL"
    resolution_analysis: Optional[Dict[str, Any]] = None
    failure_reasons: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "domain": self.domain.value if isinstance(self.domain, TroubleshootingDomain) else str(self.domain),
            "executed_steps": list(self.executed_steps),
            "hypothesis_transitions": self.hypothesis_transitions,
            "final_state": self.final_state,
            "resolution_analysis": self.resolution_analysis,
            "failure_reasons": list(self.failure_reasons),
            "timestamp": self.timestamp,
        }
