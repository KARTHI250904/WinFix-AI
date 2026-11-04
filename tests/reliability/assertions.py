"""WinFix AI — Reliability Invariant Assertions (Phase 33)."""

from typing import Any, Dict, List
from agent.safety import default_safety_engine
from agent.tool_registry import default_tool_registry
from production.telemetry_models import TelemetryEvent


def assert_security_invariants():
    """Assert all core immutable security properties across registries and engines."""
    # 1. Tool registry invariant
    tools = default_tool_registry.list_tools()
    assert len(tools) in (59, 62), f"Expected 59 or 62 tools, found {len(tools)}"

    safe_tools = [t for t in tools if t.risk.value == "SAFE"]
    med_tools = [t for t in tools if t.risk.value == "MEDIUM"]
    high_tools = [t for t in tools if t.risk.value == "HIGH"]

    assert len(safe_tools) in (49, 52)
    assert len(med_tools) == 10
    assert len(high_tools) == 0

    # 2. Medium tools require confirmation
    for med_t in med_tools:
        decision = default_safety_engine.evaluate(med_t.name, {}, user_confirmed=False)
        assert not decision.allowed, f"MEDIUM tool {med_t.name} allowed without user confirmation!"


def assert_session_isolated(session_a_events: List[TelemetryEvent], session_b_id: str):
    """Verify Session A event collection contains zero records belonging to Session B."""
    for ev in session_a_events:
        assert ev.session_id != session_b_id, f"Session leakage detected! Found {session_b_id} in {ev.session_id} event stream."
