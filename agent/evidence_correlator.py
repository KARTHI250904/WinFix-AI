"""WinFix AI — Evidence Correlator & Multi-Domain Grouping (Phase 29).

Groups evidence by domain, identifies supporting and contradictory evidence,
detects stale evidence and missing diagnostic telemetry, and establishes cross-domain relationships.
Strictly adheres to:
  Evidence != Windows Command
  Evidence Correlation is Analytical Only
  Deterministic Validation of Evidence Quality
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.domain_models import EvidenceCorrelationResult, TroubleshootingDomain
from agent.domain_registry import DomainRegistry, default_domain_registry
from agent.evidence_models import (
    EvidenceItem,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
    default_evidence_store,
)
from production.performance import default_profiler

logger = logging.getLogger("winfix.EVIDENCE_CORRELATOR")

# Mapping of EvidenceType to primary TroubleshootingDomain
EVIDENCE_TYPE_TO_DOMAIN_MAP: Dict[EvidenceType, TroubleshootingDomain] = {
    EvidenceType.NETWORK: TroubleshootingDomain.NETWORK,
    EvidenceType.PERFORMANCE: TroubleshootingDomain.PERFORMANCE,
    EvidenceType.STORAGE: TroubleshootingDomain.STORAGE,
    EvidenceType.SERVICE: TroubleshootingDomain.SERVICES,
    EvidenceType.BLUETOOTH: TroubleshootingDomain.BLUETOOTH,
    EvidenceType.WINDOWS_UPDATE: TroubleshootingDomain.WINDOWS_UPDATE,
    EvidenceType.DEFENDER: TroubleshootingDomain.WINDOWS_DEFENDER,
    EvidenceType.APPLICATION_CRASH: TroubleshootingDomain.APPLICATION_CRASH,
    EvidenceType.SYSTEM: TroubleshootingDomain.SYSTEM,
    EvidenceType.SCREENSHOT: TroubleshootingDomain.UNKNOWN,
    EvidenceType.VOICE: TroubleshootingDomain.UNKNOWN,
    EvidenceType.KNOWLEDGE: TroubleshootingDomain.UNKNOWN,
    EvidenceType.USER_REPORTED: TroubleshootingDomain.UNKNOWN,
}


class EvidenceCorrelator:
    """Analytical engine for grouping, evaluating, and correlating multi-domain diagnostic evidence."""

    def __init__(
        self,
        domain_registry: Optional[DomainRegistry] = None,
        evidence_store: Optional[EvidenceStore] = None,
    ) -> None:
        self.domain_registry = domain_registry or default_domain_registry
        self.evidence_store = evidence_store or default_evidence_store

    def correlate_evidence(
        self,
        session_id: str = "default_session",
        hint_domain: Optional[TroubleshootingDomain] = None,
    ) -> EvidenceCorrelationResult:
        """Analyze all active evidence in the session and produce a structured multi-domain correlation."""
        with default_profiler.measure("correlate_evidence"):
            items = self.evidence_store.get_session_evidence(session_id=session_id, include_stale=True)
            domain_evidence: Dict[str, List[Dict[str, Any]]] = {
                d.value: [] for d in self.domain_registry.list_domains()
            }
            stale_ids: List[str] = []
            contradictions: List[str] = []

            # Group items and check freshness / contradictions
            for item in items:
                primary_domain = EVIDENCE_TYPE_TO_DOMAIN_MAP.get(item.evidence_type, TroubleshootingDomain.UNKNOWN)
                domain_evidence[primary_domain.value].append(item.to_dict())

                if item.is_stale():
                    stale_ids.append(item.evidence_id)

                if item.status == EvidenceStatus.CONFLICTING:
                    contradictions.append(f"Evidence '{item.evidence_id}' of type '{item.evidence_type.value}' is conflicting")

            # Determine dominant domain based on verified failure evidence or hint
            domain_scores: Dict[TroubleshootingDomain, int] = {d: 0 for d in self.domain_registry.list_domains()}
            for item in items:
                if item.status == EvidenceStatus.VALID:
                    dom = EVIDENCE_TYPE_TO_DOMAIN_MAP.get(item.evidence_type, TroubleshootingDomain.UNKNOWN)
                    # Check if data indicates failure or error
                    data = item.value if isinstance(item.value, dict) else {}
                    has_error = (
                        data.get("status") in ["failed", "error", "unhealthy"]
                        or data.get("success") is False
                        or data.get("dns_resolved") is False
                        or data.get("state") == "Stopped"
                    )
                    if has_error:
                        domain_scores[dom] += 3
                    else:
                        domain_scores[dom] += 1

            # Select primary domain
            primary = hint_domain or TroubleshootingDomain.UNKNOWN
            if not hint_domain or hint_domain == TroubleshootingDomain.UNKNOWN:
                ranked = sorted(
                    [(dom, score) for dom, score in domain_scores.items() if dom != TroubleshootingDomain.UNKNOWN],
                    key=lambda x: x[1],
                    reverse=True,
                )
                if ranked and ranked[0][1] > 0:
                    primary = ranked[0][0]

            # Find secondary related domains
            secondary: List[TroubleshootingDomain] = []
            meta = self.domain_registry.get(primary)
            if meta:
                for rel in meta.related_domains:
                    if domain_scores.get(rel, 0) > 0 and rel not in secondary:
                        secondary.append(rel)

            # Identify missing required evidence for primary domain
            missing_types: List[str] = []
            if meta:
                present_types = {item.evidence_type for item in items}
                for req in meta.primary_evidence_types:
                    if req not in present_types:
                        missing_types.append(req.value)

            summary = f"Correlated {len(items)} evidence items. Primary domain: {primary.value}. "
            if secondary:
                summary += f"Secondary domains: {', '.join(d.value for d in secondary)}. "
            if missing_types:
                summary += f"Missing evidence: {', '.join(missing_types)}."

            return EvidenceCorrelationResult(
                primary_domain=primary,
                secondary_domains=secondary[:2],  # Strict maximum 2 secondary branches
                domain_evidence={k: v for k, v in domain_evidence.items() if v},
                contradictions_detected=contradictions,
                stale_evidence_ids=stale_ids,
                missing_evidence_types=missing_types,
                correlation_summary=summary,
            )


default_evidence_correlator = EvidenceCorrelator()
