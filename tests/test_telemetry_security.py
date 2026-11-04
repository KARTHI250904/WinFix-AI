"""WinFix AI — Telemetry Security & Invariant Tests (Phase 32)."""

import ast
from pathlib import Path
import pytest
import uuid

from production.telemetry_models import (
    FailureTaxonomy,
    TelemetryEvent,
    TelemetryEventType,
)
from production.telemetry import (
    TelemetryService,
    sanitize_telemetry_metadata,
)
from agent.tool_registry import default_tool_registry
from agent.safety import default_safety_engine


def test_telemetry_cannot_authorize_repairs():
    """Verify that recording a telemetry event does not grant execution authorization."""
    service = TelemetryService(db_manager=None)
    sess_id = f"test-sec-{uuid.uuid4().hex[:6]}"

    # Record spoofed authorization event
    service.record_repair_event(
        session_id=sess_id,
        event_type=TelemetryEventType.REPAIR_AUTHORIZED,
        tool_name="flush_dns_cache",
        domain="NETWORK",
    )

    # SafetyEngine must still evaluate authorization independently
    decision = default_safety_engine.evaluate(
        tool_name="flush_dns_cache",
        arguments={},
        user_confirmed=False,
    )
    # MEDIUM risk tool without explicit valid token must require confirmation
    assert not decision.allowed
    assert decision.requires_confirmation is True


def test_telemetry_sql_injection_defense():
    """Verify parameterized queries block SQL injection payloads in telemetry fields."""
    service = TelemetryService(db_manager=None)
    sess_id = "test'; DROP TABLE telemetry_events; --"

    # Writing malicious SQL payload
    res = service.record_event(
        TelemetryEvent(
            session_id=sess_id,
            event_type=TelemetryEventType.SESSION_STARTED,
            component="'; DELETE FROM sessions; --",
            metadata={"payload": "' OR '1'='1"},
        )
    )
    assert res is True

    # Querying with injection payload
    events = service.get_events(session_id=sess_id)
    assert len(events) == 1
    assert events[0].session_id == sess_id


def test_telemetry_metadata_injection_scrubbing():
    """Verify command injection patterns in metadata are neutralized."""
    malicious_meta = {
        "arg1": "powershell -NoProfile -Command Remove-Item -Recurse C:\\",
        "arg2": "cmd.exe /c echo hacked",
        "secret": "super_secret_token_abc",
    }
    clean_meta = sanitize_telemetry_metadata(malicious_meta)
    assert "secret" not in clean_meta
    assert "powershell" not in str(clean_meta.get("arg1")).lower() or "[REDACTED]" in str(clean_meta.get("arg1"))


def test_ast_scan_phase32_production_files():
    """Verify 0 prohibited execution calls in Phase 32 production modules."""
    phase32_files = [
        Path("production/telemetry_models.py"),
        Path("production/telemetry.py"),
        Path("production/telemetry_analytics.py"),
        Path("production/telemetry_retention.py"),
        Path("ui/telemetry_dashboard.py"),
    ]

    prohibited_names = {
        "subprocess",
        "popen",
        "Popen",
        "system",
        "exec",
        "eval",
        "CreateProcess",
        "WinExec",
        "ShellExecute",
    }

    for file_path in phase32_files:
        assert file_path.exists(), f"Missing file {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                assert func_name not in prohibited_names, f"Prohibited call '{func_name}' found in {file_path}"
