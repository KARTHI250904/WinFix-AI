"""WinFix AI — Telemetry & Reliability Analytics Engine (Phase 32).

Computes deterministic, neutral descriptive statistics across troubleshooting workflows,
diagnostic accuracy, repair lifecycles, recovery operations, and dependency health.
Guarantees:
  - Read-only analytics with zero execution or authorization side-effects.
  - Neutral statistics without subjective AI rankings.
"""

from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import statistics

from production.telemetry import TelemetryService, default_telemetry_service
from production.telemetry_models import (
    FailureTaxonomy,
    TelemetryEvent,
    TelemetryEventType,
)

logger = logging.getLogger("winfix.TELEMETRY_ANALYTICS")


class TelemetryAnalytics:
    """Analytics aggregator for offline troubleshooting observability."""

    def __init__(self, telemetry_service: Optional[TelemetryService] = None):
        self._telemetry = telemetry_service or default_telemetry_service

    def get_workflow_summary(
        self,
        session_id: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Aggregate high-level workflow counts and outcome distribution."""
        events = self._telemetry.get_events(session_id=session_id, limit=limit)
        workflow_events = [
            e for e in events if e.event_type.value.startswith("WORKFLOW_")
        ]

        total_started = sum(1 for e in workflow_events if e.event_type == TelemetryEventType.WORKFLOW_STARTED)
        completed = sum(1 for e in workflow_events if e.event_type == TelemetryEventType.WORKFLOW_COMPLETED)
        cancelled = sum(1 for e in workflow_events if e.event_type == TelemetryEventType.WORKFLOW_CANCELLED)
        timed_out = sum(1 for e in workflow_events if e.event_type == TelemetryEventType.WORKFLOW_TIMEOUT)
        unresolved = sum(1 for e in workflow_events if e.event_type == TelemetryEventType.WORKFLOW_UNRESOLVED)

        # Durations
        durations = [e.duration_ms for e in workflow_events if e.duration_ms is not None and e.duration_ms > 0]
        avg_dur = round(statistics.mean(durations), 1) if durations else 0.0
        med_dur = round(statistics.median(durations), 1) if durations else 0.0
        min_dur = min(durations) if durations else 0
        max_dur = max(durations) if durations else 0

        return {
            "total_workflows": total_started or (completed + cancelled + timed_out + unresolved),
            "completed": completed,
            "cancelled": cancelled,
            "timed_out": timed_out,
            "unresolved": unresolved,
            "duration_stats": {
                "average_ms": avg_dur,
                "median_ms": med_dur,
                "min_ms": min_dur,
                "max_ms": max_dur,
                "sample_size": len(durations),
            },
        }

    def get_diagnostic_effectiveness(
        self,
        session_id: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Aggregate diagnostic intelligence and hypothesis evolution metrics."""
        events = self._telemetry.get_events(session_id=session_id, limit=limit)

        hyp_created = sum(1 for e in events if e.event_type == TelemetryEventType.HYPOTHESIS_CREATED)
        hyp_supported = sum(1 for e in events if e.event_type == TelemetryEventType.HYPOTHESIS_SUPPORTED)
        hyp_contradicted = sum(1 for e in events if e.event_type == TelemetryEventType.HYPOTHESIS_CONTRADICTED)
        hyp_reassessed = sum(1 for e in events if e.event_type == TelemetryEventType.HYPOTHESIS_REASSESSED)
        hyp_resolved = sum(1 for e in events if e.event_type == TelemetryEventType.HYPOTHESIS_RESOLVED)
        hyp_unresolved = sum(1 for e in events if e.event_type == TelemetryEventType.HYPOTHESIS_UNRESOLVED)

        contradiction_rate = round(hyp_contradicted / hyp_created, 3) if hyp_created > 0 else 0.0
        reassessment_rate = round(hyp_reassessed / hyp_created, 3) if hyp_created > 0 else 0.0
        unresolved_rate = round(hyp_unresolved / hyp_created, 3) if hyp_created > 0 else 0.0

        return {
            "hypotheses_created": hyp_created,
            "hypotheses_supported": hyp_supported,
            "hypotheses_contradicted": hyp_contradicted,
            "hypotheses_reassessed": hyp_reassessed,
            "hypotheses_resolved": hyp_resolved,
            "hypotheses_unresolved": hyp_unresolved,
            "contradiction_rate": contradiction_rate,
            "reassessment_rate": reassessment_rate,
            "unresolved_rate": unresolved_rate,
        }

    def get_repair_lifecycle_stats(
        self,
        session_id: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Aggregate repair stages without collapsing them into a single success metric."""
        events = self._telemetry.get_events(session_id=session_id, limit=limit)

        candidates = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_CANDIDATE_CREATED)
        auth_required = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_AUTHORIZATION_REQUIRED)
        authorized = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_AUTHORIZED)
        auth_rejected = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_AUTHORIZATION_REJECTED)
        exec_started = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_EXECUTION_STARTED)
        exec_completed = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_EXECUTION_COMPLETED)
        exec_failed = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_EXECUTION_FAILED)
        verif_started = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_VERIFICATION_STARTED)
        verif_succeeded = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_VERIFICATION_SUCCEEDED)
        verif_failed = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_VERIFICATION_FAILED)
        resolved = sum(1 for e in events if e.event_type == TelemetryEventType.REPAIR_RESOLVED)

        return {
            "candidates_created": candidates,
            "authorizations_required": auth_required,
            "authorizations_approved": authorized,
            "authorizations_rejected": auth_rejected,
            "executions_started": exec_started,
            "executions_completed": exec_completed,
            "executions_failed": exec_failed,
            "verifications_started": verif_started,
            "verifications_succeeded": verif_succeeded,
            "verifications_failed": verif_failed,
            "resolved_repairs": resolved,
        }

    def get_recovery_summary(
        self,
        session_id: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Aggregate Phase 31 recovery, checkpoint, and replay-protection metrics."""
        events = self._telemetry.get_events(session_id=session_id, limit=limit)

        checkpoints_created = sum(1 for e in events if e.event_type == TelemetryEventType.CHECKPOINT_CREATED)
        checkpoints_restored = sum(1 for e in events if e.event_type == TelemetryEventType.CHECKPOINT_RESTORED)
        checkpoints_expired = sum(1 for e in events if e.event_type == TelemetryEventType.CHECKPOINT_EXPIRED)
        checkpoints_invalidated = sum(1 for e in events if e.event_type == TelemetryEventType.CHECKPOINT_INVALIDATED)
        recovery_started = sum(1 for e in events if e.event_type == TelemetryEventType.RECOVERY_STARTED)
        recovery_resumed = sum(1 for e in events if e.event_type == TelemetryEventType.RECOVERY_RESUMED)
        recovery_cancelled = sum(1 for e in events if e.event_type == TelemetryEventType.RECOVERY_CANCELLED)
        recovery_failed = sum(1 for e in events if e.event_type == TelemetryEventType.RECOVERY_FAILED)
        duplicate_blocked = sum(1 for e in events if e.event_type == TelemetryEventType.DUPLICATE_EXECUTION_BLOCKED)
        auth_invalidated = sum(1 for e in events if e.event_type == TelemetryEventType.AUTHORIZATION_INVALIDATED)
        stale_detected = sum(1 for e in events if e.event_type == TelemetryEventType.STALE_STATE_DETECTED)

        return {
            "checkpoints_created": checkpoints_created,
            "checkpoints_restored": checkpoints_restored,
            "checkpoints_expired": checkpoints_expired,
            "checkpoints_invalidated": checkpoints_invalidated,
            "recovery_attempts": recovery_started,
            "recovery_resumed": recovery_resumed,
            "recovery_cancelled": recovery_cancelled,
            "recovery_failed": recovery_failed,
            "duplicate_executions_blocked": duplicate_blocked,
            "authorizations_invalidated": auth_invalidated,
            "stale_states_detected": stale_detected,
        }

    def get_domain_analytics(
        self,
        session_id: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Aggregate descriptive telemetry counts by diagnostic domain."""
        events = self._telemetry.get_events(session_id=session_id, limit=limit)
        domain_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"workflows": 0, "diagnostics": 0, "unresolved": 0, "verification_failures": 0}
        )

        for e in events:
            dom = e.domain or "SYSTEM"
            if e.event_type == TelemetryEventType.WORKFLOW_STARTED:
                domain_counts[dom]["workflows"] += 1
            elif e.event_type == TelemetryEventType.DIAGNOSTIC_STARTED:
                domain_counts[dom]["diagnostics"] += 1
            elif e.event_type in (TelemetryEventType.WORKFLOW_UNRESOLVED, TelemetryEventType.HYPOTHESIS_UNRESOLVED):
                domain_counts[dom]["unresolved"] += 1
            elif e.event_type == TelemetryEventType.REPAIR_VERIFICATION_FAILED:
                domain_counts[dom]["verification_failures"] += 1

        return dict(domain_counts)

    def get_dependency_reliability_stats(
        self,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """Aggregate dependency health events across local AI, vision, voice, and system APIs."""
        events = self._telemetry.get_events(limit=limit)
        dep_events = [
            e for e in events
            if e.event_type in (TelemetryEventType.DEPENDENCY_AVAILABLE, TelemetryEventType.DEPENDENCY_UNAVAILABLE, TelemetryEventType.MODEL_AVAILABLE, TelemetryEventType.MODEL_UNAVAILABLE)
        ]

        summary: Dict[str, Dict[str, int]] = defaultdict(lambda: {"available_count": 0, "unavailable_count": 0})
        for e in dep_events:
            dep_name = e.tool_name or e.component or "unknown"
            if e.event_type in (TelemetryEventType.DEPENDENCY_AVAILABLE, TelemetryEventType.MODEL_AVAILABLE):
                summary[dep_name]["available_count"] += 1
            else:
                summary[dep_name]["unavailable_count"] += 1

        return dict(summary)

    def get_recent_failures(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent sanitized failure occurrences."""
        events = self._telemetry.get_events(limit=limit * 5)
        failures = [
            e for e in events
            if e.failure_type != FailureTaxonomy.NONE or e.event_type in (
                TelemetryEventType.WORKFLOW_TIMEOUT,
                TelemetryEventType.WORKFLOW_CANCELLED,
                TelemetryEventType.REPAIR_EXECUTION_FAILED,
                TelemetryEventType.REPAIR_VERIFICATION_FAILED,
                TelemetryEventType.RECOVERY_FAILED,
            )
        ][:limit]

        return [
            {
                "timestamp_utc": f.timestamp_utc,
                "session_id": f.session_id,
                "event_type": f.event_type.value if isinstance(f.event_type, TelemetryEventType) else str(f.event_type),
                "component": f.component,
                "domain": f.domain,
                "tool_name": f.tool_name,
                "failure_type": f.failure_type.value if isinstance(f.failure_type, FailureTaxonomy) else str(f.failure_type),
                "metadata": f.metadata,
            }
            for f in failures
        ]

    def get_overall_reliability_metrics(self) -> Dict[str, Any]:
        """Unified overview for telemetry dashboard and health checking."""
        wf = self.get_workflow_summary()
        diag = self.get_diagnostic_effectiveness()
        rep = self.get_repair_lifecycle_stats()
        rec = self.get_recovery_summary()

        return {
            "workflows": wf,
            "diagnostics": diag,
            "repairs": rep,
            "recovery": rec,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }


# Global singleton instance
default_telemetry_analytics = TelemetryAnalytics()
