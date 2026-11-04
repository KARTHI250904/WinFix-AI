"""WinFix AI — Fuzz & Malformed Input Tests (Phase 33)."""

import pytest
from agent.agent_response import parse_agent_response
from production.telemetry_models import TelemetryEvent, TelemetryEventType
from production.telemetry import sanitize_telemetry_metadata


def test_fuzz_agent_response_with_garbage_unicode():
    """Verify parser handles null bytes, emoji storms, and huge strings safely."""
    fuzz_inputs = [
        "",
        "\x00\x00\x00",
        "🔥" * 5000,
        "null",
        "undefined",
        "NaN",
        "[]",
        '{"unknown_key": true, "nested": {"deep": {"structure": 123}}}',
    ]

    for garbage in fuzz_inputs:
        success, resp, err = parse_agent_response(garbage)
        assert isinstance(success, bool)


def test_fuzz_telemetry_metadata_structures():
    """Verify recursive or pathological metadata structures are bounded and sanitized."""
    pathological_dict = {
        f"key_{i}": {"nested": "value" * 100} for i in range(100)
    }
    cleaned = sanitize_telemetry_metadata(pathological_dict)
    assert len(cleaned) <= 25 or "truncated" in cleaned
