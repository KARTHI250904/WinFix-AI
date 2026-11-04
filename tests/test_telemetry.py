"""WinFix AI — Telemetry Core & Sanitization Tests (Phase 32)."""

import json
import pytest
from datetime import datetime, timezone
import uuid

from production.telemetry_models import (
    FailureTaxonomy,
    TelemetryEvent,
    TelemetryEventType,
    TelemetrySeverity,
)
from production.telemetry import (
    TelemetryService,
    sanitize_telemetry_metadata,
    sanitize_telemetry_value,
)


def test_telemetry_event_creation_and_defaults():
    event = TelemetryEvent(
        session_id="test_sess_01",
        event_type=TelemetryEventType.SESSION_STARTED,
        component="test_suite",
        severity=TelemetrySeverity.INFO,
    )
    assert event.event_id is not None
    assert event.session_id == "test_sess_01"
    assert event.event_type == TelemetryEventType.SESSION_STARTED
    assert event.component == "test_suite"
    assert event.failure_type == FailureTaxonomy.NONE
    assert event.schema_version == "1.0"


def test_telemetry_serialization_roundtrip():
    event = TelemetryEvent(
        session_id="sess_rt",
        event_type=TelemetryEventType.WORKFLOW_COMPLETED,
        component="workflow_engine",
        duration_ms=120,
        domain="NETWORK",
        tool_name="flush_dns_cache",
        failure_type=FailureTaxonomy.NONE,
        outcome="COMPLETED",
        metadata={"step_count": 3, "resolved": True},
    )
    d = event.to_dict()
    assert d["session_id"] == "sess_rt"
    assert d["event_type"] == "WORKFLOW_COMPLETED"
    assert d["duration_ms"] == 120
    assert d["domain"] == "NETWORK"
    assert d["tool_name"] == "flush_dns_cache"

    restored = TelemetryEvent.from_dict(d)
    assert restored.session_id == "sess_rt"
    assert restored.event_type == TelemetryEventType.WORKFLOW_COMPLETED
    assert restored.duration_ms == 120
    assert restored.metadata.get("step_count") == 3


def test_privacy_sanitization_strips_forbidden_keys():
    raw_meta = {
        "password": "SuperSecretPassword123!",
        "auth_token": "bearer xyz-987654",
        "api_key": "sk-1234567890",
        "cookie": "session_cookie=abc",
        "command_line": "powershell -enc aW52b2tl",
        "safe_metric": 42,
        "domain": "STORAGE",
    }
    clean_meta = sanitize_telemetry_metadata(raw_meta)
    assert "password" not in clean_meta
    assert "auth_token" not in clean_meta
    assert "api_key" not in clean_meta
    assert "cookie" not in clean_meta
    assert "command_line" not in clean_meta
    assert clean_meta.get("safe_metric") == 42
    assert clean_meta.get("domain") == "STORAGE"


def test_privacy_sanitization_scrubs_sensitive_patterns():
    val = sanitize_telemetry_value("header", "Authorization: Bearer token_secret_123456")
    assert "Bearer [REDACTED]" in val or "[REDACTED]" in val
    assert "token_secret_123456" not in val

    cmd_val = sanitize_telemetry_value("info", "Executing powershell -ExecutionPolicy Bypass")
    assert "powershell" not in cmd_val.lower() or "[REDACTED]" in cmd_val


def test_privacy_sanitization_bounds_string_length():
    huge_str = "A" * 1000
    cleaned = sanitize_telemetry_value("data", huge_str)
    assert len(cleaned) <= 300
    assert "[TRUNCATED]" in cleaned


def test_telemetry_service_in_memory_and_fallback():
    service = TelemetryService(db_manager=None)
    sess_id = f"test-sess-{uuid.uuid4().hex[:6]}"

    service.record_session_event(session_id=sess_id, event_type=TelemetryEventType.SESSION_STARTED)
    service.record_diagnostic_event(
        session_id=sess_id,
        event_type=TelemetryEventType.DIAGNOSTIC_STARTED,
        domain="NETWORK",
        tool_name="check_dns_resolution",
    )
    service.record_repair_event(
        session_id=sess_id,
        event_type=TelemetryEventType.REPAIR_CANDIDATE_CREATED,
        tool_name="flush_dns_cache",
        domain="NETWORK",
    )

    events = service.get_events(session_id=sess_id)
    assert len(events) == 3
    event_types = [e.event_type for e in events]
    assert TelemetryEventType.SESSION_STARTED in event_types
    assert TelemetryEventType.DIAGNOSTIC_STARTED in event_types
    assert TelemetryEventType.REPAIR_CANDIDATE_CREATED in event_types
