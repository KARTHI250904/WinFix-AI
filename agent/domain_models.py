"""WinFix AI — Advanced Troubleshooting Domain Models (Phase 29).

Defines strongly-typed domain definitions, classifications, evidence correlation structures,
and standardized failure categories.
Strictly adheres to:
  Domain Classification != Execution Authority
  Strategy Selection != Repair Authorization
  Failure Classification != LLM Hallucination
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("winfix.DOMAIN_MODELS")


class TroubleshootingDomain(str, Enum):
    """Authoritative, allowlisted Windows troubleshooting domains."""

    NETWORK = "NETWORK"
    PERFORMANCE = "PERFORMANCE"
    STORAGE = "STORAGE"
    SERVICES = "SERVICES"
    WINDOWS_UPDATE = "WINDOWS_UPDATE"
    WINDOWS_DEFENDER = "WINDOWS_DEFENDER"
    BLUETOOTH = "BLUETOOTH"
    APPLICATION_CRASH = "APPLICATION_CRASH"
    DISPLAY = "DISPLAY"
    AUDIO = "AUDIO"
    PRINTER = "PRINTER"
    STARTUP = "STARTUP"
    SYSTEM = "SYSTEM"
    UNKNOWN = "UNKNOWN"


class FailureCategory(str, Enum):
    """Standardized failure categories across troubleshooting workflows."""

    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class DomainClassification:
    """Structured domain classification resulting from symptom analysis and factual evidence."""

    domain: TroubleshootingDomain
    status: str = "POSSIBLE"  # POSSIBLE, SUPPORTED, CONTRADICTED, UNRESOLVED, VERIFIED
    confidence: float = 1.0
    supporting_evidence_ids: List[str] = field(default_factory=list)
    contradicting_evidence_ids: List[str] = field(default_factory=list)
    secondary_domains: List[TroubleshootingDomain] = field(default_factory=list)
    source: str = "deterministic_rules"  # "deterministic_rules", "ai_assisted", "tool_verified"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert classification to dictionary."""
        return {
            "domain": self.domain.value if isinstance(self.domain, TroubleshootingDomain) else str(self.domain),
            "status": self.status,
            "confidence": self.confidence,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "secondary_domains": [
                d.value if isinstance(d, TroubleshootingDomain) else str(d)
                for d in self.secondary_domains
            ],
            "source": self.source,
            "created_at": self.created_at,
        }


@dataclass
class EvidenceCorrelationResult:
    """Structured result of multi-domain evidence grouping and correlation."""

    primary_domain: TroubleshootingDomain
    secondary_domains: List[TroubleshootingDomain] = field(default_factory=list)
    domain_evidence: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    contradictions_detected: List[str] = field(default_factory=list)
    stale_evidence_ids: List[str] = field(default_factory=list)
    missing_evidence_types: List[str] = field(default_factory=list)
    correlation_summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert correlation result to dictionary."""
        return {
            "primary_domain": self.primary_domain.value if isinstance(self.primary_domain, TroubleshootingDomain) else str(self.primary_domain),
            "secondary_domains": [
                d.value if isinstance(d, TroubleshootingDomain) else str(d)
                for d in self.secondary_domains
            ],
            "domain_evidence": dict(self.domain_evidence),
            "contradictions_detected": list(self.contradictions_detected),
            "stale_evidence_ids": list(self.stale_evidence_ids),
            "missing_evidence_types": list(self.missing_evidence_types),
            "correlation_summary": self.correlation_summary,
            "created_at": self.created_at,
        }
