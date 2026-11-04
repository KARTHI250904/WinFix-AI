"""WinFix AI — Telemetry & Reliability Models (Phase 32).

Defines strongly typed immutable models, event taxonomies, and failure taxonomies
for offline, privacy-preserving Windows troubleshooting telemetry and analytics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict, List, Optional
import uuid


class TelemetryEventType(str, Enum):
    """Deterministic event taxonomy across all troubleshooting lifecycles."""

    # Session Lifecycle
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_COMPLETED = "SESSION_COMPLETED"
    SESSION_CANCELLED = "SESSION_CANCELLED"
    SESSION_FAILED = "SESSION_FAILED"

    # Workflow Lifecycle
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    WORKFLOW_STEP_STARTED = "WORKFLOW_STEP_STARTED"
    WORKFLOW_STEP_COMPLETED = "WORKFLOW_STEP_COMPLETED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_CANCELLED = "WORKFLOW_CANCELLED"
    WORKFLOW_TIMEOUT = "WORKFLOW_TIMEOUT"
    WORKFLOW_UNRESOLVED = "WORKFLOW_UNRESOLVED"

    # Diagnostic Lifecycle
    DIAGNOSTIC_STARTED = "DIAGNOSTIC_STARTED"
    DIAGNOSTIC_COMPLETED = "DIAGNOSTIC_COMPLETED"
    HYPOTHESIS_CREATED = "HYPOTHESIS_CREATED"
    HYPOTHESIS_SUPPORTED = "HYPOTHESIS_SUPPORTED"
    HYPOTHESIS_CONTRADICTED = "HYPOTHESIS_CONTRADICTED"
    HYPOTHESIS_REASSESSED = "HYPOTHESIS_REASSESSED"
    HYPOTHESIS_RESOLVED = "HYPOTHESIS_RESOLVED"
    HYPOTHESIS_UNRESOLVED = "HYPOTHESIS_UNRESOLVED"

    # Evidence Lifecycle
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    EVIDENCE_MUTATED = "EVIDENCE_MUTATED"
    EVIDENCE_CONTRADICTED = "EVIDENCE_CONTRADICTED"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"

    # Repair Lifecycle (Distinct, Non-Collapsing States)
    REPAIR_CANDIDATE_CREATED = "REPAIR_CANDIDATE_CREATED"
    REPAIR_AUTHORIZATION_REQUIRED = "REPAIR_AUTHORIZATION_REQUIRED"
    REPAIR_AUTHORIZED = "REPAIR_AUTHORIZED"
    REPAIR_AUTHORIZATION_REJECTED = "REPAIR_AUTHORIZATION_REJECTED"
    REPAIR_EXECUTION_STARTED = "REPAIR_EXECUTION_STARTED"
    REPAIR_EXECUTION_COMPLETED = "REPAIR_EXECUTION_COMPLETED"
    REPAIR_EXECUTION_FAILED = "REPAIR_EXECUTION_FAILED"
    REPAIR_VERIFICATION_STARTED = "REPAIR_VERIFICATION_STARTED"
    REPAIR_VERIFICATION_SUCCEEDED = "REPAIR_VERIFICATION_SUCCEEDED"
    REPAIR_VERIFICATION_FAILED = "REPAIR_VERIFICATION_FAILED"
    REPAIR_RESOLVED = "REPAIR_RESOLVED"

    # Recovery Lifecycle (Phase 31)
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    CHECKPOINT_RESTORED = "CHECKPOINT_RESTORED"
    CHECKPOINT_EXPIRED = "CHECKPOINT_EXPIRED"
    CHECKPOINT_INVALIDATED = "CHECKPOINT_INVALIDATED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_STATE_REVALIDATED = "RECOVERY_STATE_REVALIDATED"
    RECOVERY_RESUMED = "RECOVERY_RESUMED"
    RECOVERY_CANCELLED = "RECOVERY_CANCELLED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    DUPLICATE_EXECUTION_BLOCKED = "DUPLICATE_EXECUTION_BLOCKED"
    AUTHORIZATION_INVALIDATED = "AUTHORIZATION_INVALIDATED"
    STALE_STATE_DETECTED = "STALE_STATE_DETECTED"

    # Model & Dependency Lifecycle
    MODEL_AVAILABLE = "MODEL_AVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_ERROR = "MODEL_ERROR"
    DEPENDENCY_AVAILABLE = "DEPENDENCY_AVAILABLE"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class FailureTaxonomy(str, Enum):
    """Deterministic failure classification across all subsystems."""

    NONE = "NONE"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    AUTHORIZATION_INVALID = "AUTHORIZATION_INVALID"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    UNRESOLVED = "UNRESOLVED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    STALE_STATE = "STALE_STATE"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    INVALID_INPUT = "INVALID_INPUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


class TelemetrySeverity(str, Enum):
    """Severity tier for telemetry events."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class TelemetryEvent:
    """Strongly typed immutable telemetry event record.
    
    Contains strictly sanitized metadata, timing, domain, and failure classification.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = "default_session"
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    event_type: TelemetryEventType = TelemetryEventType.SESSION_STARTED
    component: str = "core"
    schema_version: str = "1.0"
    severity: TelemetrySeverity = TelemetrySeverity.INFO
    duration_ms: Optional[int] = None
    domain: Optional[str] = None
    tool_name: Optional[str] = None
    failure_type: FailureTaxonomy = FailureTaxonomy.NONE
    outcome: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary format for SQLite persistence or logging."""
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type.value if isinstance(self.event_type, Enum) else str(self.event_type),
            "component": self.component,
            "schema_version": self.schema_version,
            "severity": self.severity.value if isinstance(self.severity, Enum) else str(self.severity),
            "duration_ms": self.duration_ms,
            "domain": self.domain,
            "tool_name": self.tool_name,
            "failure_type": self.failure_type.value if isinstance(self.failure_type, Enum) else str(self.failure_type),
            "outcome": self.outcome,
            "metadata": self.metadata,
            "created_at": self.created_at or self.timestamp_utc,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetryEvent":
        """Deserialize dictionary to TelemetryEvent with validation."""
        raw_event_type = data.get("event_type", TelemetryEventType.SESSION_STARTED.value)
        try:
            event_type = TelemetryEventType(raw_event_type)
        except ValueError:
            event_type = TelemetryEventType.SESSION_STARTED

        raw_failure = data.get("failure_type", FailureTaxonomy.NONE.value)
        try:
            failure_type = FailureTaxonomy(raw_failure)
        except ValueError:
            failure_type = FailureTaxonomy.NONE

        raw_severity = data.get("severity", TelemetrySeverity.INFO.value)
        try:
            severity = TelemetrySeverity(raw_severity)
        except ValueError:
            severity = TelemetrySeverity.INFO

        meta = data.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        return cls(
            event_id=str(data.get("event_id", str(uuid.uuid4()))),
            session_id=str(data.get("session_id", "default_session")),
            timestamp_utc=str(data.get("timestamp_utc", datetime.now(timezone.utc).isoformat())),
            event_type=event_type,
            component=str(data.get("component", "core")),
            schema_version=str(data.get("schema_version", "1.0")),
            severity=severity,
            duration_ms=data.get("duration_ms"),
            domain=data.get("domain"),
            tool_name=data.get("tool_name"),
            failure_type=failure_type,
            outcome=data.get("outcome"),
            metadata=meta if isinstance(meta, dict) else {},
            created_at=data.get("created_at"),
        )
