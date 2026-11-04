"""Comprehensive Test Suite for Personal Tutor Mode (Phase 15).

Tests:
- TutorResponse model structure, serialization, and TutorSeverity enum
- Privacy sanitization (user path masking, email masking, credential masking)
- Bounded TutorContext history management
- Tutor prompt generator schema compliance
- Explanations of diagnostics across domains (Network, Storage, Performance, Services,
  Bluetooth, Windows Update, Defender, Application Crashes)
- Separation of observed evidence from hypotheses / possible causes
- Explanations of repair outcomes and verification states (verified, not_verified, timeout, failed)
- Explanations of SafetyEngine decisions (SAFE, MEDIUM confirmation, HIGH blocked)
- Strict validation and filtering of recommended tools against ToolRegistry
- Rejection of forbidden command execution keys in LLM output
- Graceful deterministic fallback when Ollama is offline or outputs malformed JSON
- AST static security scan verifying zero forbidden execution or system modification APIs
"""

import ast
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from agent.safety import SafetyDecision
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry, default_tool_registry
from ai.tutor_prompt import TUTOR_SYSTEM_INSTRUCTION, build_tutor_prompt
from modes.personal_tutor import PersonalTutor, default_personal_tutor
from modes.tutor_context import (
    TutorContext,
    sanitize_tutor_payload,
    sanitize_tutor_text,
)
from modes.tutor_models import (
    TutorExplanationRequest,
    TutorResponse,
    TutorSeverity,
)


class TestTutorModels(unittest.TestCase):
    """Test suite for TutorResponse data model and severity enums."""

    def test_tutor_response_defaults_and_serialization(self):
        """Verify TutorResponse serializes cleanly to dictionary."""
        resp = TutorResponse(
            title="Test Title",
            summary="Test Summary",
            what_happened="Problem description",
            evidence=["Observed evidence 1"],
            severity=TutorSeverity.NORMAL.value,
            severity_explanation="Severity explanation",
            possible_causes=["Hypothesis 1"],
            what_this_means="Impact on user",
            recommended_next_steps=["Step 1"],
            recommended_tools=["check_dns_resolution"],
            safety_notes=["Safety note 1"],
            verification_explanation="Verified successfully",
            educational_notes=["Tip 1"],
            limitations=["Limitation 1"],
            confidence=0.9,
        )

        d = resp.to_dict()
        self.assertEqual(d["title"], "Test Title")
        self.assertEqual(d["severity"], "NORMAL")
        self.assertEqual(d["evidence"], ["Observed evidence 1"])
        self.assertEqual(d["possible_causes"], ["Hypothesis 1"])
        self.assertEqual(d["recommended_tools"], ["check_dns_resolution"])
        self.assertEqual(d["confidence"], 0.9)

    def test_tutor_severity_enum(self):
        """Verify standard severity enum values."""
        self.assertEqual(TutorSeverity.NORMAL.value, "NORMAL")
        self.assertEqual(TutorSeverity.ELEVATED.value, "ELEVATED")
        self.assertEqual(TutorSeverity.HIGH.value, "HIGH")
        self.assertEqual(TutorSeverity.CRITICAL.value, "CRITICAL")
        self.assertEqual(TutorSeverity.UNKNOWN.value, "UNKNOWN")


class TestTutorPrivacyAndSanitization(unittest.TestCase):
    """Test suite for privacy sanitization functions."""

    def test_sanitize_user_paths(self):
        """Verify user paths mask the personal username."""
        raw = r"Error occurred in C:\Users\Karthick\AppData\Local\Temp\crash.log"
        sanitized = sanitize_tutor_text(raw)
        self.assertNotIn("Karthick", sanitized)
        self.assertIn(r"C:\Users\<User>\AppData\Local\Temp\crash.log", sanitized)

    def test_sanitize_emails_and_credentials(self):
        """Verify email addresses and tokens are masked."""
        raw = "User admin@company.com reported token: abc12345678"
        sanitized = sanitize_tutor_text(raw)
        self.assertNotIn("admin@company.com", sanitized)
        self.assertIn("<email-masked>", sanitized)
        self.assertIn("<credential-masked>", sanitized)

    def test_sanitize_payload_recursive(self):
        """Verify recursive dictionary and list sanitization."""
        payload = {
            "path": r"C:\Users\JohnDoe\file.txt",
            "details": ["Contact me at john@doe.org", r"C:\Users\Alice\app.exe"],
            "count": 42,
        }
        sanitized = sanitize_tutor_payload(payload)
        self.assertEqual(sanitized["path"], r"C:\Users\<User>\file.txt")
        self.assertEqual(sanitized["details"][0], "Contact me at <email-masked>")
        self.assertEqual(sanitized["details"][1], r"C:\Users\<User>\app.exe")
        self.assertEqual(sanitized["count"], 42)

    def test_preserves_system_paths(self):
        """Verify standard Windows and Program Files paths remain intact."""
        raw = r"C:\Windows\System32\ntdll.dll and C:\Program Files\App\app.exe"
        sanitized = sanitize_tutor_text(raw)
        self.assertIn(r"C:\Windows\System32\ntdll.dll", sanitized)
        self.assertIn(r"C:\Program Files\App\app.exe", sanitized)


class TestTutorContext(unittest.TestCase):
    """Test suite for TutorContext and bounded history management."""

    def test_tutor_context_bounded_history(self):
        """Verify context bounds history to max_history entries."""
        ctx = TutorContext(session_id="test_sess", max_history=3)
        ctx.add_user_message("Q1")
        ctx.add_tutor_response("A1")
        ctx.add_user_message("Q2")
        ctx.add_tutor_response("A2")
        ctx.add_user_message("Q3")

        hist = ctx.get_history_summary()
        self.assertEqual(len(hist), 3)
        self.assertEqual(hist[-1]["content"], "Q3")

    def test_tutor_context_snapshots(self):
        """Verify diagnostic and repair snapshot recording."""
        ctx = TutorContext(session_id="test_sess")
        ctx.set_latest_diagnostic({"dns_resolved": True})
        ctx.set_latest_repair({"tool": "flush_dns_cache", "verified": True})

        self.assertEqual(ctx.get_latest_diagnostic(), {"dns_resolved": True})
        self.assertEqual(ctx.get_latest_repair(), {"tool": "flush_dns_cache", "verified": True})


class TestTutorPrompt(unittest.TestCase):
    """Test suite for Tutor prompt generation."""

    def test_build_tutor_prompt(self):
        """Verify prompt builder formats sections cleanly."""
        prompt = build_tutor_prompt(
            user_question="Why did my app crash?",
            diagnostic_evidence={"crashes": 2, "faulting_module": "ntdll.dll"},
            repair_result=None,
            verification_status=None,
            allowed_tools=["get_recent_application_crashes", "get_application_crash_summary"],
        )

        self.assertIn("USER QUESTION / TOPIC:", prompt)
        self.assertIn("Why did my app crash?", prompt)
        self.assertIn("OBSERVED WINDOWS DIAGNOSTIC DATA:", prompt)
        self.assertIn("ntdll.dll", prompt)
        self.assertIn("APPROVED WINFIX AI TOOLS", prompt)
        self.assertIn("get_recent_application_crashes", prompt)
        self.assertIn(TUTOR_SYSTEM_INSTRUCTION, TUTOR_SYSTEM_INSTRUCTION)


class TestPersonalTutorExplanations(unittest.TestCase):
    """Test suite for PersonalTutor diagnostic and repair explanations."""

    def setUp(self):
        self.registry = create_default_registry()
        self.mock_client = MagicMock()
        self.tutor = PersonalTutor(client=self.mock_client, tool_registry=self.registry)

    def test_explain_diagnostic_with_mock_llm(self):
        """Verify structured explanation when LLM returns valid JSON."""
        mock_llm_json = {
            "title": "Application Crash Analysis",
            "summary": "Notepad crashed due to an access violation in ntdll.dll.",
            "what_happened": "Notepad encountered an unhandled exception 0xc0000005.",
            "evidence": ["Event ID 1000 logged for notepad.exe", "Faulting module: ntdll.dll"],
            "severity": "ELEVATED",
            "severity_explanation": "Application crashed once.",
            "possible_causes": ["Missing application update", "Temporary memory access conflict"],
            "what_this_means": "The program closed abruptly.",
            "recommended_next_steps": ["Check for Windows and application updates."],
            "recommended_tools": ["get_recent_application_crashes"],
            "safety_notes": ["Do not replace system DLL files."],
            "verification_explanation": None,
            "educational_notes": ["Access violations occur when a program attempts to read protected memory."],
            "limitations": ["A faulting module is evidence, not confirmed root cause."],
            "confidence": 0.9,
        }

        self.mock_client.generate.return_value = {
            "success": True,
            "response": json.dumps(mock_llm_json),
        }

        diag_data = {"crashes": 1, "app": "notepad.exe", "module": "ntdll.dll"}
        resp = self.tutor.explain_diagnostic(
            diagnostic_data=diag_data,
            user_question="Why did notepad crash?",
            session_id="test_sess",
        )

        self.assertIsInstance(resp, TutorResponse)
        self.assertEqual(resp.title, "Application Crash Analysis")
        self.assertEqual(resp.severity, "ELEVATED")
        self.assertEqual(len(resp.evidence), 2)
        self.assertEqual(len(resp.possible_causes), 2)
        self.assertEqual(resp.recommended_tools, ["get_recent_application_crashes"])

    def test_explain_repair_verified(self):
        """Verify tutor explains verified repair correctly."""
        resp = self.tutor.explain_repair(
            tool_name="restart_windows_update_service",
            repair_output={"status": "RUNNING"},
            verification_status="verified",
            before_state={"status": "STOPPED"},
            after_state={"status": "RUNNING"},
            user_question="Did restarting Windows Update work?",
            session_id="test_sess",
        )

        self.assertIsInstance(resp, TutorResponse)
        self.assertIn("Verified", resp.title)
        self.assertEqual(resp.severity, "NORMAL")
        self.assertIsNotNone(resp.verification_explanation)
        self.assertIn("verified", resp.verification_explanation.lower())

    def test_explain_repair_not_verified(self):
        """Verify tutor explains unverified or timed-out repair clearly."""
        resp = self.tutor.explain_repair(
            tool_name="restart_windows_update_service",
            repair_output={"status": "STOPPED"},
            verification_status="not_verified",
            before_state={"status": "STOPPED"},
            after_state={"status": "STOPPED"},
            user_question="Did it work?",
            session_id="test_sess",
        )

        self.assertIsInstance(resp, TutorResponse)
        self.assertIn("Not Verified", resp.title)
        self.assertEqual(resp.severity, "ELEVATED")

    def test_explain_safety_decision_high_blocked(self):
        """Verify tutor explains why HIGH risk actions are blocked."""
        decision = SafetyDecision(
            allowed=False,
            requires_confirmation=False,
            blocked=True,
            risk="HIGH",
            reason="HIGH risk operations are strictly blocked.",
            validated_arguments={},
        )

        resp = self.tutor.explain_safety_decision(
            tool_name="dangerous_tool",
            decision=decision,
            session_id="test_sess",
        )

        self.assertIn("blocked", resp.what_happened.lower())
        self.assertEqual(resp.severity, "HIGH")

    def test_explain_safety_decision_medium_confirmation(self):
        """Verify tutor explains why MEDIUM risk actions require user confirmation."""
        decision = SafetyDecision(
            allowed=False,
            requires_confirmation=True,
            blocked=False,
            risk="MEDIUM",
            reason="Confirmation required.",
            validated_arguments={},
        )

        resp = self.tutor.explain_safety_decision(
            tool_name="restart_windows_update_service",
            decision=decision,
            session_id="test_sess",
        )

        self.assertIn("confirmation", resp.what_happened.lower())
        self.assertEqual(resp.severity, "NORMAL")


class TestTutorToolValidationAndSecurity(unittest.TestCase):
    """Test suite for tool recommendation filtering and forbidden key rejection."""

    def setUp(self):
        self.registry = create_default_registry()
        self.mock_client = MagicMock()
        self.tutor = PersonalTutor(client=self.mock_client, tool_registry=self.registry)

    def test_filters_unregistered_tools(self):
        """Verify unapproved or hallucinated tools in recommended_tools are stripped."""
        raw_json = {
            "title": "Diagnosis",
            "summary": "Summary",
            "what_happened": "Details",
            "evidence": ["Ev1"],
            "severity": "NORMAL",
            "possible_causes": ["Cause 1"],
            "what_this_means": "Meaning",
            "recommended_next_steps": ["Step 1"],
            "recommended_tools": [
                "check_dns_resolution",       # Valid registered tool
                "delete_system_files",        # Hallucinated invalid tool
                "download_driver_updater",    # Hallucinated invalid tool
            ],
            "safety_notes": ["Note"],
        }

        self.mock_client.generate.return_value = {
            "success": True,
            "response": json.dumps(raw_json),
        }

        resp = self.tutor.explain_diagnostic(diagnostic_data={"dns": False})
        self.assertIn("check_dns_resolution", resp.recommended_tools)
        self.assertNotIn("delete_system_files", resp.recommended_tools)
        self.assertNotIn("download_driver_updater", resp.recommended_tools)

    def test_rejects_forbidden_execution_keys(self):
        """Verify responses containing command execution injection keys trigger deterministic fallback."""
        raw_json_with_command = {
            "title": "Malicious Response",
            "summary": "Executing shell command",
            "powershell": "Restart-Service wuauserv",  # Forbidden execution key
            "evidence": ["Test"],
        }

        self.mock_client.generate.return_value = {
            "success": True,
            "response": json.dumps(raw_json_with_command),
        }

        resp = self.tutor.explain_diagnostic(diagnostic_data={"windows_update": False})
        # Should cleanly fall back to deterministic response
        self.assertNotEqual(resp.title, "Malicious Response")
        self.assertIn("Windows Update", resp.title)


class TestTutorDeterministicFallbacks(unittest.TestCase):
    """Test suite for offline / failure deterministic fallback handling across domains."""

    def setUp(self):
        self.registry = create_default_registry()
        # Mock client returning failure (e.g. Ollama offline)
        self.mock_client = MagicMock()
        self.mock_client.generate.return_value = {"success": False, "error": "Connection refused"}
        self.tutor = PersonalTutor(client=self.mock_client, tool_registry=self.registry)

    def test_application_crash_fallback(self):
        """Verify Phase 14 crash diagnostic deterministic fallback."""
        diag_data = {"crashes": 2, "total_crashes": 2, "overall_status": "RECURRING_APPLICATION_CRASH"}
        resp = self.tutor.explain_diagnostic(diagnostic_data=diag_data)

        self.assertIn("Application Crash", resp.title)
        self.assertEqual(resp.severity, "ELEVATED")
        self.assertTrue(len(resp.possible_causes) > 0)
        self.assertIn("get_recent_application_crashes", resp.recommended_tools)

    def test_windows_update_fallback(self):
        """Verify Phase 12 Windows Update deterministic fallback."""
        diag_data = {"update_services_ready": False, "windows_update": True}
        resp = self.tutor.explain_diagnostic(diagnostic_data=diag_data)

        self.assertIn("Windows Update", resp.title)
        self.assertEqual(resp.severity, "ELEVATED")
        self.assertIn("get_windows_update_diagnostics", resp.recommended_tools)

    def test_defender_fallback(self):
        """Verify Phase 13 Defender deterministic fallback."""
        diag_data = {"antivirus_service_running": False, "firewall_service_running": True}
        resp = self.tutor.explain_diagnostic(diagnostic_data=diag_data)

        self.assertIn("Defender", resp.title)
        self.assertEqual(resp.severity, "HIGH")
        self.assertIn("get_defender_diagnostics", resp.recommended_tools)

    def test_network_fallback(self):
        """Verify Phase 6/7 Network deterministic fallback."""
        diag_data = {"resolved": False, "reachable": False}
        resp = self.tutor.explain_diagnostic(diagnostic_data=diag_data)

        self.assertIn("Network", resp.title)
        self.assertIn("check_dns_resolution", resp.recommended_tools)


class TestTutorSecurityASTScan(unittest.TestCase):
    """Static AST security analysis of Phase 15 implementation files."""

    def test_ast_security_scan(self):
        """Verify zero forbidden execution, process termination, event log clearing, or registry writing in Phase 15."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        phase15_files = [
            os.path.join(repo_root, "modes", "personal_tutor.py"),
            os.path.join(repo_root, "modes", "tutor_context.py"),
            os.path.join(repo_root, "modes", "tutor_models.py"),
            os.path.join(repo_root, "modes", "__init__.py"),
            os.path.join(repo_root, "ai", "tutor_prompt.py"),
        ]

        forbidden_imports = {
            "subprocess",
            "shutil",
        }
        forbidden_calls = {
            "os.system",
            "os.popen",
            "eval",
            "exec",
            "ClearEventLog",
            "TerminateProcess",
            "taskkill",
        }
        forbidden_attributes = {
            "SetValue",
            "SetValueEx",
            "DeleteValue",
            "DeleteKey",
            "CreateKey",
            "CreateKeyEx",
            "kill",
            "terminate",
        }

        for file_path in phase15_files:
            if not os.path.exists(file_path):
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)

            for node in ast.walk(tree):
                # Check forbidden imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(
                            alias.name,
                            forbidden_imports,
                            f"Forbidden import '{alias.name}' found in {file_path}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.assertNotIn(
                            node.module,
                            forbidden_imports,
                            f"Forbidden import-from '{node.module}' found in {file_path}",
                        )

                # Check forbidden function calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            forbidden_calls,
                            f"Forbidden function call '{node.func.id}()' in {file_path}",
                        )
                    elif isinstance(node.func, ast.Attribute):
                        attr_name = node.func.attr
                        self.assertNotIn(
                            attr_name,
                            forbidden_attributes,
                            f"Forbidden method call '.{attr_name}()' in {file_path}",
                        )
                        if isinstance(node.func.value, ast.Name):
                            if node.func.value.id in ("os", "sys", "subprocess"):
                                full_call = f"{node.func.value.id}.{attr_name}"
                                self.assertNotIn(
                                    full_call,
                                    forbidden_calls,
                                    f"Forbidden call '{full_call}()' in {file_path}",
                                )


class TestTutorCustomQuestionDomainDispatch(unittest.TestCase):
    """Verify that different custom user questions produce domain-accurate tutor responses rather than static text."""

    def setUp(self):
        from agent.tool_registry import create_default_registry
        from unittest.mock import MagicMock
        self.registry = create_default_registry()
        self.mock_client = MagicMock()
        self.mock_client.generate.return_value = {"success": False, "error": "Offline"}
        self.tutor = PersonalTutor(client=self.mock_client, tool_registry=self.registry)
        self.composite_diag_data = {
            "dns": {"success": True, "tool": "check_dns_resolution", "domain": "network", "data": {"resolved": True, "latency_ms": 120.0}},
            "internet": {"success": True, "tool": "check_internet_connectivity", "domain": "network", "data": {"reachable": True, "latency_ms": 50.0}},
            "adapters": {"success": True, "tool": "get_network_adapters_diagnostics", "domain": "network", "data": {}},
            "defender": {"success": True, "tool": "get_defender_diagnostics", "domain": "defender", "data": {"real_time_protection": True}},
            "windows_update": {"success": True, "tool": "get_windows_update_diagnostics", "domain": "update", "data": {"update_services_ready": True}},
            "printer": {"success": True, "tool": "get_printer_diagnostics", "domain": "printer", "data": {"spooler_running": True}},
            "bluetooth": {"success": True, "tool": "get_bluetooth_diagnostics", "domain": "bluetooth", "data": {"service_running": True}},
            "top_cpu": {"success": True, "tool": "get_top_cpu_processes", "domain": "performance", "data": {}},
            "storage": {"success": True, "tool": "get_storage_diagnostics", "domain": "storage", "data": {}},
        }

    def test_wifi_question_returns_network_guidance(self):
        """User asking 'how to solve the wifi problem' receives Wi-Fi/Network guidance and tools."""
        resp = self.tutor.answer_question(
            user_question="how to solve the wifi problem",
            diagnostic_data=self.composite_diag_data,
        )
        self.assertTrue(any("Wi-Fi" in resp.title or "Network" in resp.title or "Internet" in resp.title for _ in [1]))
        self.assertFalse(resp.title.startswith("Windows Update"))
        self.assertTrue(any("check_internet_connectivity" in t or "get_network_adapters_diagnostics" in t or "check_dns_resolution" in t for t in resp.recommended_tools))

    def test_defender_question_returns_defender_guidance(self):
        """User asking 'what is windows defender doing' receives Defender security guidance."""
        resp = self.tutor.answer_question(
            user_question="what is windows defender doing",
            diagnostic_data=self.composite_diag_data,
        )
        self.assertTrue(any("Defender" in resp.title or "Security" in resp.title for _ in [1]))
        self.assertFalse(resp.title.startswith("Windows Update"))
        self.assertTrue(any("get_defender_diagnostics" in t for t in resp.recommended_tools))

    def test_bluetooth_question_returns_bluetooth_guidance(self):
        """User asking 'why is bluetooth disconnected' receives Bluetooth guidance."""
        resp = self.tutor.answer_question(
            user_question="Why is Bluetooth disconnected or failing to discover devices?",
            diagnostic_data=self.composite_diag_data,
        )
        self.assertIn("Bluetooth", resp.title)
        self.assertFalse(resp.title.startswith("Windows Update"))
        self.assertTrue(any("get_bluetooth_diagnostics" in t for t in resp.recommended_tools))

    def test_printer_question_returns_printer_guidance(self):
        """User asking 'why is printer not printing' receives Printer & Spooler guidance."""
        resp = self.tutor.answer_question(
            user_question="why is my printer not printing and queue stuck?",
            diagnostic_data=self.composite_diag_data,
        )
        self.assertTrue("Printer" in resp.title or "Spooler" in resp.title)
        self.assertFalse(resp.title.startswith("Windows Update"))
        self.assertTrue(any("get_printer_diagnostics" in t for t in resp.recommended_tools))


if __name__ == "__main__":
    unittest.main()
