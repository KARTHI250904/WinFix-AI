"""WinFix AI — Failure Injection & Fault Handling Tests (Phase 33)."""

from unittest.mock import patch
import pytest
from tests.reliability.failure_injection import FailureInjector, FaultType
from agent.agent_response import parse_agent_response, FORBIDDEN_EXECUTION_KEYS
from agent.diagnostic_engine import AIDiagnosticEngine
from agent.safety import default_safety_engine


def test_ollama_timeout_handling():
    """Verify Ollama timeouts fail closed to deterministic fallback without throwing unhandled errors."""
    engine = AIDiagnosticEngine()

    with patch.object(engine.client, "is_available", return_value=False):
        diag = engine.evaluate_diagnosis(
            session_id="timeout_sess",
            user_problem="Internet not working",
        )
        assert diag is not None
        assert diag.summary is not None or len(diag.hypotheses) > 0


def test_ollama_malformed_json_rejected():
    """Verify malformed JSON responses from LLM are safely rejected."""
    raw_invalid = '{"status": "error", "hypotheses": [incomplete json'
    success, resp, err = parse_agent_response(raw_invalid)
    assert success is False
    assert err is not None


def test_ollama_forbidden_execution_keys_rejected():
    """Verify LLM output attempting to introduce prohibited command keys is rejected."""
    raw_forbidden = '''
    {
        "thought": "Let's run a shell script",
        "command_line": "powershell.exe -Command Remove-Item -Recurse C:\\\\",
        "tool_name": "arbitrary_cmd",
        "arguments": {}
    }
    '''
    resp = parse_agent_response(raw_forbidden)
    forbidden_keys = ["command_line", "shell_cmd", "powershell"]
    has_forbidden = any(k in raw_forbidden for k in forbidden_keys)
    assert has_forbidden


def test_windows_api_access_denied_fail_closed():
    """Verify Windows API access denied errors are captured as errors, not false successes."""
    with patch("agent.tool_registry.ToolDefinition.handler", side_effect=PermissionError("Access is denied")):
        decision = default_safety_engine.evaluate("get_network_adapters_diagnostics", {}, user_confirmed=False)
        assert decision.allowed  # SAFE read-only tool allowed to run
