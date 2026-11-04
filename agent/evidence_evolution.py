"""WinFix AI — Evidence Evolution & Before/After Tracking (Phase 30).

Tracks evidence progression over time, computes metric deltas, detects factual mutations,
stale states, newly emerged contradictions, and builds before/after comparison records.
Strictly adheres to:
  Execution Success != Verification Success
  Telemetry Facts > Unverified Model Assertions
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from agent.adaptive_models import (
    BeforeAfterComparison,
    EvidenceChange,
    EvidenceChangeType,
)
from agent.evidence_models import EvidenceItem, EvidenceQuality, EvidenceStore

logger = logging.getLogger("winfix.EVIDENCE_EVOLUTION")


class EvidenceEvolutionTracker:
    """Session-scoped tracker for telemetry evolution and before/after action comparisons."""

    def __init__(self, evidence_store: EvidenceStore) -> None:
        self.evidence_store = evidence_store

    def track_change(
        self,
        old_evidence: Optional[EvidenceItem],
        new_evidence: EvidenceItem,
        reason: str = "",
    ) -> EvidenceChange:
        """Evaluate differences between previous evidence and freshly collected evidence."""
        if old_evidence is None:
            change_type = EvidenceChangeType.NEW
            old_val = None
        elif old_evidence.is_stale():
            change_type = EvidenceChangeType.STALE
            old_val = old_evidence.value if isinstance(old_evidence.value, dict) else {"raw": old_evidence.value}
        elif self._is_contradictory(old_evidence, new_evidence):
            change_type = EvidenceChangeType.CONTRADICTED
            old_val = old_evidence.value if isinstance(old_evidence.value, dict) else {"raw": old_evidence.value}
        elif old_evidence.value != new_evidence.value:
            change_type = EvidenceChangeType.MUTATED
            old_val = old_evidence.value if isinstance(old_evidence.value, dict) else {"raw": old_evidence.value}
        else:
            change_type = EvidenceChangeType.UNCHANGED
            old_val = old_evidence.value if isinstance(old_evidence.value, dict) else {"raw": old_evidence.value}

        new_val = new_evidence.value if isinstance(new_evidence.value, dict) else {"raw": new_evidence.value}
        change = EvidenceChange(
            evidence_id=new_evidence.evidence_id,
            evidence_type=new_evidence.evidence_type.value if hasattr(new_evidence.evidence_type, "value") else str(new_evidence.evidence_type),
            change_type=change_type,
            old_value=old_val,
            new_value=new_val,
            reason=reason or f"Evidence state evaluated as {change_type.value}",
        )
        return change


    def compute_before_after_comparison(
        self,
        tool_name: str,
        pre_evidence: Dict[str, Any],
        post_evidence: Dict[str, Any],
        verification_passed: bool,
        details: str = "",
    ) -> BeforeAfterComparison:
        """Compute structured before/after comparison with metric deltas."""
        metric_deltas: Dict[str, Any] = {}
        state_changed = False

        # Compute metric differences where numerical keys exist
        all_keys = set(pre_evidence.keys()).union(post_evidence.keys())
        for k in all_keys:
            pre_v = pre_evidence.get(k)
            post_v = post_evidence.get(k)
            if isinstance(pre_v, bool) or isinstance(post_v, bool):
                if pre_v != post_v:
                    state_changed = True
                    metric_deltas[f"{k}_changed"] = {"from": pre_v, "to": post_v}
            elif isinstance(pre_v, (int, float)) and isinstance(post_v, (int, float)):
                metric_deltas[f"{k}_delta"] = post_v - pre_v
                if pre_v != post_v:
                    state_changed = True
            elif pre_v != post_v:
                state_changed = True
                metric_deltas[f"{k}_changed"] = {"from": pre_v, "to": post_v}


        comparison = BeforeAfterComparison(
            comparison_id=str(uuid.uuid4()),
            tool_name=tool_name,
            pre_evidence=pre_evidence,
            post_evidence=post_evidence,
            metric_deltas=metric_deltas,
            state_changed=state_changed,
            verification_passed=verification_passed,
            details=details or f"Before/after comparison for tool '{tool_name}' evaluated. Passed: {verification_passed}",
        )
        return comparison

    def _is_contradictory(self, a: EvidenceItem, b: EvidenceItem) -> bool:
        """Check if two evidence items for the same component convey diametrically opposed facts."""
        if a.evidence_type != b.evidence_type:
            return False

        a_data = a.value if isinstance(a.value, dict) else {}
        b_data = b.value if isinstance(b.value, dict) else {}

        # Service contradictions (e.g. running vs stopped)
        a_status = a_data.get("status") or a_data.get("state")
        b_status = b_data.get("status") or b_data.get("state")
        if a_status and b_status and str(a_status).lower() != str(b_status).lower():
            return True

        # DNS resolution contradictions
        a_dns = a_data.get("dns_resolved") or a_data.get("resolved")
        b_dns = b_data.get("dns_resolved") or b_data.get("resolved")
        if a_dns is not None and b_dns is not None and bool(a_dns) != bool(b_dns):
            return True

        # Network connectivity contradictions
        a_conn = a_data.get("connected") or a_data.get("internet_accessible")
        b_conn = b_data.get("connected") or b_data.get("internet_accessible")
        if a_conn is not None and b_conn is not None and bool(a_conn) != bool(b_conn):
            return True

        return False

