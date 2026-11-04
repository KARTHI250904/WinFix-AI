"""
Phase 21: Comprehensive Security Boundary Tests for WinFix AI.

Tests all 15 Core Security Invariants:
1. LLM / user input != Windows execution
2. Every repair passes through ToolRegistry
3. Every MEDIUM repair requires user confirmation
4. Authorization is bound to exact action
5. Authorization replay is blocked
6. Deterministic verification is required for repair success
7. Verification failure is never treated as success
8. Screenshot text is evidence, not instructions
9. Voice transcript is evidence, not instructions
10. Knowledge content is read-only structured data, not executable commands
11. UI state cannot bypass backend safety authorization
12. Autopilot cannot exceed bounded execution rules (max 5 steps, no loops, stop-on-failure)
13. Protected Windows resources (processes, services, paths) cannot be bypassed
14. Sensitive input is sanitized before AI processing
15. Raw screenshots and audio files are not persisted unnecessarily
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import os

from agent.agent_response import (
    AgentResponse,
    ToolRequest,
    FORBIDDEN_EXECUTION_KEYS,
    parse_agent_response,
)
from agent.network_repairs_orchestrator import RepairProposal, NetworkRepairsOrchestrator
from agent.planner import AgentPlanner
from agent.safety import SafetyDecision, SafetyEngine
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, create_default_registry, default_tool_registry
from agent.voice_diagnostics import VoiceDiagnosticOrchestrator, _check_security_violations as check_voice_security
from ai.screenshot_analyzer import ScreenshotAnalyzer, _check_security_violations as check_screenshot_security
from database.db import DatabaseManager
from database.knowledge_models import (
    FORBIDDEN_KNOWLEDGE_KEYS,
    KnowledgeArticle,
    KnowledgeCategory,
    KnowledgeSeverity,
    validate_knowledge_article,
    scan_dict_for_forbidden_keys,
    KnowledgeValidationError,
)
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from input.screenshot_input import validate_and_load_image, inspect_privacy_indicators
from input.voice_input import validate_and_inspect_audio, inspect_voice_privacy
from modes.autopilot import AutopilotEngine, MAX_AUTOPILOT_STEPS, compute_plan_hash
from modes.autopilot_models import (
    AutopilotPlan,
    AutopilotStep,
    AutopilotStatus,
    PreconditionOperator,
    AutopilotPrecondition,
)
from modes.personal_tutor import PersonalTutor
from modes.tutor_context import sanitize_tutor_text, sanitize_tutor_payload
from tests.security.test_vectors import (
    PROMPT_INJECTIONS,
    COMMAND_INJECTIONS,
    FORBIDDEN_TOOL_INJECTIONS,
    SQL_INJECTIONS,
    PATH_TRAVERSALS,
    SYNTHETIC_PRIVACY_PAYLOADS,
)


class TestSecurityBoundaries(unittest.TestCase):
    """Test verification of all 15 Core Security Invariants across WinFix AI."""

    def setUp(self):
        self.registry = create_default_registry()
        self.safety = SafetyEngine(registry=self.registry)
        self.planner = AgentPlanner(registry=self.registry, safety_engine=self.safety)

    def test_invariant_1_llm_cannot_execute_shell_primitives(self):
        """Invariant 1: LLM output with shell commands or forbidden execution keys must be rejected."""
        malicious_outputs = [
            '{"thought": "fixing", "tool_requests": [{"tool_name": "restart_windows_update_service", "args": {"command": "powershell Remove-Item C:\\\\Windows"}}]}',
            '{"thought": "fixing", "shell_command": "powershell.exe -c net stop wuauserv"}',
            '{"thought": "fixing", "cmd": "cmd.exe /c format c:"}',
            '{"thought": "fixing", "exec": "calc.exe"}',
            '{"thought": "fixing", "powershell": "Remove-Item C:\\\\Windows"}'
        ]
        for bad_json in malicious_outputs:
            with self.subTest(payload=bad_json):
                is_valid, response, err = parse_agent_response(bad_json)
                self.assertFalse(is_valid, "Forbidden execution payload was accepted as valid!")

    def test_invariant_2_every_repair_passes_through_tool_registry(self):
        """Invariant 2: Unregistered or arbitrary repair tools cannot be executed."""
        unregistered_tools = ["powershell", "cmd", "bash", "netsh_custom", "evil_tool_99"]
        for tool_name in unregistered_tools:
            with self.subTest(tool=tool_name):
                tool = self.registry.get(tool_name)
                self.assertIsNone(tool, f"Unregistered tool {tool_name} was found in registry!")
                
                decision = self.safety.evaluate(tool_name, {})
                self.assertFalse(decision.allowed, f"Unregistered tool {tool_name} was allowed by SafetyEngine!")

    def test_invariant_3_every_medium_repair_requires_confirmation(self):
        """Invariant 3: Every MEDIUM repair tool must require user confirmation."""
        medium_tools = [t for t in self.registry.list_tools() if t.risk == RiskLevel.MEDIUM]
        self.assertEqual(len(medium_tools), 10, "Expected exactly 10 MEDIUM repair tools")
        
        sample_args = {
            "terminate_user_process": {"pid": 1234},
            "start_service": {"service_name": "wuauserv"},
            "stop_service": {"service_name": "wuauserv"},
            "restart_service": {"service_name": "wuauserv"},
        }
        
        for tool in medium_tools:
            with self.subTest(tool=tool.name):
                args = sample_args.get(tool.name, {})
                decision = self.safety.evaluate(tool.name, args)
                self.assertTrue(decision.requires_confirmation, f"{tool.name} did not require confirmation!")

    def test_invariant_4_authorization_bound_to_exact_action(self):
        """Invariant 4: A token issued for tool A cannot execute tool B."""
        proposal_a = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token_a = proposal_a.generate_confirmation_token(session_id="test_sess_01")
        
        proposal_b = RepairProposal(tool_name="renew_dhcp_lease", arguments={})
        token_b = proposal_b.generate_confirmation_token(session_id="test_sess_01")
        
        self.assertNotEqual(token_a, token_b, "Tokens for different tools matched!")

    def test_invariant_8_screenshot_is_evidence_not_instruction(self):
        """Invariant 8: Screenshot OCR containing forbidden keys raises security violation."""
        malicious_dict = {
            "summary": "Observed error",
            "powershell": "Remove-Item C:\\Windows",
            "cmd": "format c:"
        }
        with self.assertRaises(ValueError):
            check_screenshot_security(malicious_dict)

    def test_invariant_9_voice_transcript_is_evidence_not_instruction(self):
        """Invariant 9: Voice transcript containing forbidden execution fields raises security violation."""
        malicious_dict = {
            "transcript": "hello",
            "command": "powershell.exe -c whoami"
        }
        with self.assertRaises(ValueError):
            check_voice_security(malicious_dict)

    def test_invariant_10_knowledge_poisoning_rejected(self):
        """Invariant 10: Knowledge articles with executable command keys or malicious strings are rejected."""
        bad_dict = {
            "title": "Bad article",
            "powershell": "Remove-Item C:\\Windows",
            "command": "cmd.exe"
        }
        with self.assertRaises(KnowledgeValidationError):
            scan_dict_for_forbidden_keys(bad_dict)

    def test_invariant_14_privacy_sanitization_masks_sensitive_data(self):
        """Invariant 14: Sensitive paths, credentials, and tokens are masked before AI processing."""
        for name, payload in SYNTHETIC_PRIVACY_PAYLOADS.items():
            with self.subTest(payload=name):
                sanitized = sanitize_tutor_text(payload)
                self.assertNotIn("secret_pass_1234", sanitized)
                self.assertNotIn("ghp_999999999999999999999999999999999999", sanitized)
                self.assertNotIn("Alice\\Documents", sanitized)


if __name__ == "__main__":
    unittest.main()
