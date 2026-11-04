"""WinFix AI — Production Telemetry & Observability Service (Phase 32).

Provides local-only, privacy-preserving, SQLite-backed telemetry recording.
Guarantees:
  - Telemetry cannot authorize or execute repairs.
  - Telemetry cannot alter verification or override recovery.
  - Strictly no raw screenshots, raw audio, credentials, secrets, or shell commands stored.
  - Failures in telemetry logging never crash application or troubleshooting workflows.
"""

from datetime import datetime, timezone
from enum import Enum
import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional
import uuid

from production.telemetry_models import (
    FailureTaxonomy,
    TelemetryEvent,
    TelemetryEventType,
    TelemetrySeverity,
)

logger = logging.getLogger("winfix.TELEMETRY")

# Sensitive keyword patterns to sanitize/scrub
SENSITIVE_PATTERNS = [
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]+['\"]?", re.IGNORECASE),
    re.compile(r"password\s*[:=]\s*['\"]?[^\s'\"]+['\"]?", re.IGNORECASE),
    re.compile(r"secret\s*[:=]\s*['\"]?[^\s'\"]+['\"]?", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]+['\"]?", re.IGNORECASE),
    re.compile(r"(powershell|cmd\.exe|bash|sh)\s+-[a-zA-Z0-9_\-]+", re.IGNORECASE),
]

FORBIDDEN_KEYS = {
    "password", "secret", "token", "auth_token", "api_key", "credentials",  # forbidden sensitive keys for redaction
    "cookie", "raw_audio", "audio_bytes", "raw_screenshot", "image_bytes",
    "prompt", "raw_prompt", "model_response", "command_line", "shell_cmd",
}

MAX_METADATA_KEYS = 25
MAX_STRING_LENGTH = 256
MAX_JSON_BYTES = 4096


def sanitize_telemetry_value(key: str, value: Any) -> Any:
    """Sanitize a single metadata value."""
    if key.lower() in FORBIDDEN_KEYS:
        return "[REDACTED]"

    if isinstance(value, bytes):
        return "[BINARY_DATA_STRIPPED]"

    if isinstance(value, str):
        # Scrub sensitive patterns
        sanitized = value
        for pattern in SENSITIVE_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        if len(sanitized) > MAX_STRING_LENGTH:
            sanitized = sanitized[:MAX_STRING_LENGTH] + "...[TRUNCATED]"
        return sanitized

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, list):
        return [sanitize_telemetry_value(f"{key}_item", item) for item in value[:10]]

    if isinstance(value, dict):
        return sanitize_telemetry_metadata(value)

    return str(value)[:MAX_STRING_LENGTH]


def sanitize_telemetry_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize metadata dictionary, enforcing key boundaries and stripping secrets."""
    if not isinstance(metadata, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for k, v in list(metadata.items())[:MAX_METADATA_KEYS]:
        clean_key = str(k)[:64]
        if clean_key.lower() in FORBIDDEN_KEYS:
            continue
        sanitized[clean_key] = sanitize_telemetry_value(clean_key, v)

    # Check serialized size boundary
    try:
        encoded = json.dumps(sanitized)
        if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
            return {"truncated": True, "notice": "Metadata exceeded size limits"}
    except Exception:
        return {"error": "Non-serializable metadata"}

    return sanitized


class TelemetryService:
    """Production telemetry recorder with SQLite storage and in-memory fallback."""

    def __init__(self, db_manager: Optional[Any] = None):
        self._db_manager = db_manager
        self._lock = threading.Lock()
        self._memory_events: List[TelemetryEvent] = []
        self._max_memory_events = 2000

    def _get_connection(self):
        """Get database connection safely."""
        try:
            if self._db_manager is not None:
                return self._db_manager.get_connection()
            from database.db import get_db
            return get_db().get_connection()
        except Exception:
            return None

    def record_event(self, event: TelemetryEvent) -> bool:
        """Record a telemetry event safely. Fails closed to logging, never crashing caller."""
        try:
            # 1. Sanitize event metadata
            clean_metadata = sanitize_telemetry_metadata(event.metadata)
            clean_event = TelemetryEvent(
                event_id=event.event_id,
                session_id=event.session_id,
                timestamp_utc=event.timestamp_utc,
                event_type=event.event_type,
                component=str(event.component)[:64],
                schema_version=event.schema_version,
                severity=event.severity,
                duration_ms=event.duration_ms,
                domain=str(event.domain)[:64] if event.domain else None,
                tool_name=str(event.tool_name)[:64] if event.tool_name else None,
                failure_type=event.failure_type,
                outcome=str(event.outcome)[:64] if event.outcome else None,
                metadata=clean_metadata,
                created_at=event.created_at or event.timestamp_utc,
            )

            # 2. Append to memory buffer
            with self._lock:
                self._memory_events.append(clean_event)
                if len(self._memory_events) > self._max_memory_events:
                    self._memory_events.pop(0)

            # 3. Persist to SQLite if available
            conn = self._get_connection()
            if conn is not None:
                with self._lock:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO telemetry_events (
                                event_id, session_id, timestamp_utc, event_type,
                                component, schema_version, severity, duration_ms,
                                domain, tool_name, failure_type, outcome, metadata_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                clean_event.event_id,
                                clean_event.session_id,
                                clean_event.timestamp_utc,
                                clean_event.event_type.value if isinstance(clean_event.event_type, TelemetryEventType) else str(clean_event.event_type),
                                clean_event.component,
                                clean_event.schema_version,
                                clean_event.severity.value if isinstance(clean_event.severity, TelemetrySeverity) else str(clean_event.severity),
                                clean_event.duration_ms,
                                clean_event.domain,
                                clean_event.tool_name,
                                clean_event.failure_type.value if isinstance(clean_event.failure_type, FailureTaxonomy) else str(clean_event.failure_type),
                                clean_event.outcome,
                                json.dumps(clean_event.metadata),
                                clean_event.created_at,
                            ),
                        )
                        conn.commit()
                    except Exception as db_err:
                        logger.warning(f"Failed to persist telemetry event to SQLite: {db_err}")
            return True
        except Exception as ex:
            logger.error(f"Telemetry recording error (non-fatal): {ex}")
            return False

    def record_session_event(
        self,
        session_id: str,
        event_type: TelemetryEventType,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        failure_type: FailureTaxonomy = FailureTaxonomy.NONE,
    ) -> bool:
        """Record session lifecycle events."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=event_type,
                component="session",
                duration_ms=duration_ms,
                failure_type=failure_type,
                metadata=metadata or {},
            )
        )

    def record_workflow_event(
        self,
        session_id: str,
        event_type: TelemetryEventType,
        domain: Optional[str] = None,
        duration_ms: Optional[int] = None,
        outcome: Optional[str] = None,
        failure_type: FailureTaxonomy = FailureTaxonomy.NONE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record workflow lifecycle events."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=event_type,
                component="workflow_engine",
                domain=domain,
                duration_ms=duration_ms,
                outcome=outcome,
                failure_type=failure_type,
                metadata=metadata or {},
            )
        )

    def record_diagnostic_event(
        self,
        session_id: str,
        event_type: TelemetryEventType,
        domain: Optional[str] = None,
        tool_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        failure_type: FailureTaxonomy = FailureTaxonomy.NONE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record diagnostic intelligence events."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=event_type,
                component="diagnostic_engine",
                domain=domain,
                tool_name=tool_name,
                duration_ms=duration_ms,
                failure_type=failure_type,
                metadata=metadata or {},
            )
        )

    def record_evidence_event(
        self,
        session_id: str,
        event_type: TelemetryEventType,
        domain: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record evidence collection and mutation events."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=event_type,
                component="evidence_store",
                domain=domain,
                metadata=metadata or {},
            )
        )

    def record_repair_event(
        self,
        session_id: str,
        event_type: TelemetryEventType,
        tool_name: str,
        domain: Optional[str] = None,
        duration_ms: Optional[int] = None,
        outcome: Optional[str] = None,
        failure_type: FailureTaxonomy = FailureTaxonomy.NONE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record repair lifecycle events."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=event_type,
                component="repair_orchestrator",
                domain=domain,
                tool_name=tool_name,
                duration_ms=duration_ms,
                outcome=outcome,
                failure_type=failure_type,
                metadata=metadata or {},
            )
        )

    def record_recovery_event(
        self,
        session_id: str,
        event_type: TelemetryEventType,
        domain: Optional[str] = None,
        failure_type: FailureTaxonomy = FailureTaxonomy.NONE,
        outcome: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record recovery and resumption lifecycle events."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=event_type,
                component="recovery_manager",
                domain=domain,
                failure_type=failure_type,
                outcome=outcome,
                metadata=metadata or {},
            )
        )

    def record_failure(
        self,
        session_id: str,
        failure_type: FailureTaxonomy,
        component: str,
        domain: Optional[str] = None,
        tool_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """Record an explicit deterministic failure event."""
        return self.record_event(
            TelemetryEvent(
                session_id=session_id,
                event_type=TelemetryEventType.SESSION_FAILED,
                component=component,
                severity=TelemetrySeverity.ERROR,
                domain=domain,
                tool_name=tool_name,
                failure_type=failure_type,
                metadata={"details": str(details)[:MAX_STRING_LENGTH]} if details else {},
            )
        )

    def record_dependency_event(
        self,
        dependency_name: str,
        available: bool,
        details: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Record dependency availability (Ollama, Vision, Voice, Windows API)."""
        event_type = (
            TelemetryEventType.DEPENDENCY_AVAILABLE
            if available
            else TelemetryEventType.DEPENDENCY_UNAVAILABLE
        )
        return self.record_event(
            TelemetryEvent(
                session_id="system",
                event_type=event_type,
                component="dependency_manager",
                tool_name=dependency_name,
                duration_ms=duration_ms,
                failure_type=FailureTaxonomy.NONE if available else FailureTaxonomy.DEPENDENCY_UNAVAILABLE,
                metadata={"details": str(details)[:MAX_STRING_LENGTH]} if details else {},
            )
        )

    def get_events(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[TelemetryEventType] = None,
        limit: int = 100,
    ) -> List[TelemetryEvent]:
        """Fetch telemetry events matching query from SQLite or memory buffer."""
        conn = self._get_connection()
        if conn is not None:
            try:
                cursor = conn.cursor()
                query = "SELECT event_id, session_id, timestamp_utc, event_type, component, schema_version, severity, duration_ms, domain, tool_name, failure_type, outcome, metadata_json, created_at FROM telemetry_events WHERE 1=1"
                params: List[Any] = []
                if session_id:
                    query += " AND session_id = ?"
                    params.append(session_id)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type.value if isinstance(event_type, Enum) else str(event_type))
                query += " ORDER BY timestamp_utc DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                results: List[TelemetryEvent] = []
                for row in rows:
                    results.append(
                        TelemetryEvent.from_dict({
                            "event_id": row[0],
                            "session_id": row[1],
                            "timestamp_utc": row[2],
                            "event_type": row[3],
                            "component": row[4],
                            "schema_version": row[5],
                            "severity": row[6],
                            "duration_ms": row[7],
                            "domain": row[8],
                            "tool_name": row[9],
                            "failure_type": row[10],
                            "outcome": row[11],
                            "metadata": row[12],
                            "created_at": row[13],
                        })
                    )
                return results
            except Exception as ex:
                logger.warning(f"Error querying telemetry SQLite: {ex}")

        # Fallback to memory buffer
        with self._lock:
            filtered = list(self._memory_events)
            if session_id:
                filtered = [e for e in filtered if e.session_id == session_id]
            if event_type:
                filtered = [e for e in filtered if e.event_type == event_type]
            return sorted(filtered, key=lambda e: e.timestamp_utc, reverse=True)[:limit]


# Global singleton instance
default_telemetry_service = TelemetryService()
