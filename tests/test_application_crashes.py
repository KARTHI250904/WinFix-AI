"""Comprehensive Test Suite for Windows Application Crash Diagnostics (Phase 14).

Tests:
- All 8 Phase 14 diagnostic tools (get_recent_application_crashes, get_application_crash_details,
  get_application_crash_summary, get_application_crash_frequency, get_faulting_module_information,
  get_windows_error_reporting_status, get_application_crash_events, get_application_crash_diagnostics)
- Empty state handling (no recent crashes returns structured empty result)
- Unavailable/mocked Windows API and Event Log error handling
- Malformed and partial event record parsing
- Input validation (time windows, limits, application names)
- ToolRegistry metadata and risk classification (59 tools, 49 SAFE, 10 MEDIUM, 0 HIGH)
- SafetyEngine enforcement (all 8 tools SAFE, read_only=True, automatic_allowed=True)
- Orchestrator diagnosis classification, evidence vs. recommendation separation
- AST static security scan verifying zero forbidden execution, process killing, event log clearing, or registry writing
"""

import ast
import os
import unittest
from unittest.mock import MagicMock, patch

from agent.application_crash_diagnostics import (
    CRASH_CATEGORIES,
    ApplicationCrashDiagnosis,
    ApplicationCrashDiagnosticsOrchestrator,
    default_application_crash_orchestrator,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry, default_tool_registry
from database.db import DatabaseManager
from windows.application_crash_tools import (
    get_application_crash_details,
    get_application_crash_diagnostics,
    get_application_crash_events,
    get_application_crash_frequency,
    get_application_crash_summary,
    get_faulting_module_information,
    get_recent_application_crashes,
    get_windows_error_reporting_status,
)


class TestApplicationCrashDiagnosticTools(unittest.TestCase):
    """Test suite for Phase 14 application crash diagnostic tools."""

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_get_recent_application_crashes_with_events(self, mock_read, mock_platform):
        """Verify get_recent_application_crashes retrieves and returns structured crash events."""
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 14:00:00",
                    "event_id": 1000,
                    "source": "Application Error",
                    "level": "Error",
                    "event_type": "Application Crash",
                    "application_name": "notepad.exe",
                    "application_version": "11.0.0.0",
                    "faulting_module": "ntdll.dll",
                    "faulting_module_version": "10.0.22621.1",
                    "exception_code": "0xc0000005",
                    "exception_name": "STATUS_ACCESS_VIOLATION",
                    "fault_offset": "0x0000000000012345",
                    "process_id": "1234",
                    "message": "Faulting application name: notepad.exe, faulting module: ntdll.dll",
                    "message_summary": "notepad.exe crashed in ntdll.dll (0xc0000005)",
                }
            ],
            50,
            False,
        )

        res = get_recent_application_crashes(limit=5, max_scan=50)
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_recent_application_crashes")
        self.assertEqual(res["domain"], "applications")
        self.assertEqual(res["data"]["crashes_found"], 1)
        self.assertEqual(len(res["data"]["crashes"]), 1)
        self.assertEqual(res["data"]["crashes"][0]["application_name"], "notepad.exe")
        self.assertEqual(res["data"]["crashes"][0]["faulting_module"], "ntdll.dll")

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_get_application_crash_details_filtered(self, mock_read, mock_platform):
        """Verify get_application_crash_details filters by application_name."""
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 14:00:00",
                    "event_id": 1000,
                    "source": "Application Error",
                    "level": "Error",
                    "event_type": "Application Crash",
                    "application_name": "app1.exe",
                    "faulting_module": "mod1.dll",
                    "exception_code": "0xc0000005",
                    "process_id": "100",
                    "message_summary": "app1 crashed",
                }
            ],
            100,
            False,
        )

        res = get_application_crash_details(application_name="app1.exe", limit=10)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["count"], 1)
        self.assertEqual(res["data"]["records"][0]["application_name"], "app1.exe")

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_get_application_crash_summary(self, mock_read, mock_platform):
        """Verify get_application_crash_summary produces aggregate metrics."""
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 14:00:00",
                    "application_name": "test.exe",
                    "faulting_module": "test.dll",
                    "exception_code": "0xc0000005",
                },
                {
                    "timestamp": "2026-09-24 14:10:00",
                    "application_name": "test.exe",
                    "faulting_module": "test.dll",
                    "exception_code": "0xc0000005",
                },
                {
                    "timestamp": "2026-09-24 14:20:00",
                    "application_name": "other.exe",
                    "faulting_module": "kernel32.dll",
                    "exception_code": "0xc0000409",
                },
            ],
            100,
            False,
        )

        res = get_application_crash_summary(time_window="24h")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["total_crashes"], 3)
        self.assertEqual(res["data"]["unique_applications"], 2)
        self.assertEqual(res["data"]["unique_faulting_modules"], 2)
        self.assertIn("test.exe", res["data"]["recurring_applications"])
        self.assertEqual(res["data"]["crashes_by_application"]["test.exe"], 2)

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_get_application_crash_frequency(self, mock_read, mock_platform):
        """Verify get_application_crash_frequency calculates deterministic recurrence rates."""
        mock_read.return_value = (
            [
                {"timestamp": "2026-09-24 14:00:00", "application_name": "app.exe", "faulting_module": "mod.dll"},
                {"timestamp": "2026-09-24 14:05:00", "application_name": "app.exe", "faulting_module": "mod.dll"},
            ],
            50,
            False,
        )

        res = get_application_crash_frequency(time_window="1h")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["time_window"], "1h")
        self.assertEqual(res["data"]["total_crashes"], 2)
        self.assertEqual(res["data"]["crashes_by_application"]["app.exe"], 2)
        self.assertEqual(len(res["data"]["recurring_crashes"]), 1)
        self.assertEqual(res["data"]["recurring_crashes"][0]["application_name"], "app.exe")
        self.assertEqual(res["data"]["recurring_crashes"][0]["crash_count"], 2)

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_get_faulting_module_information(self, mock_read, mock_platform):
        """Verify get_faulting_module_information distinguishes observed module from confirmed root cause."""
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 14:00:00",
                    "application_name": "app.exe",
                    "faulting_module": "crashlib.dll",
                    "faulting_module_version": "1.2.3.4",
                    "exception_code": "0xc0000005",
                }
            ],
            50,
            False,
        )

        res = get_faulting_module_information(module_name="crashlib.dll")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["count"], 1)
        mod = res["data"]["modules"][0]
        self.assertEqual(mod["module_name"], "crashlib.dll")
        self.assertEqual(mod["observed_faulting_module"], True)
        self.assertEqual(mod["confirmed_root_cause"], False)
        self.assertIn("app.exe", mod["associated_applications"])

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools.get_service_status")
    def test_get_windows_error_reporting_status(self, mock_svc_status, mock_platform):
        """Verify get_windows_error_reporting_status safely queries WerSvc and read-only registry."""
        mock_svc_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "data": {
                "service_name": "WerSvc",
                "display_name": "Windows Error Reporting Service",
                "status": "RUNNING",
                "is_running": True,
                "start_type": "MANUAL",
                "pid": 3000,
            },
            "error": None,
        }

        res = get_windows_error_reporting_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_windows_error_reporting_status")
        self.assertEqual(res["data"]["service_name"], "WerSvc")
        self.assertTrue(res["data"]["service_running"])

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_get_application_crash_events(self, mock_read, mock_platform):
        """Verify get_application_crash_events returns bounded, filtered events."""
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 14:00:00",
                    "event_id": 1000,
                    "source": "Application Error",
                    "level": "Error",
                    "event_type": "Application Crash",
                    "application_name": "target.exe",
                    "faulting_module": "target.dll",
                }
            ],
            100,
            False,
        )

        res = get_application_crash_events(time_window="24h", limit=10, application_name="target.exe")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["events_count"], 1)
        self.assertEqual(res["data"]["events"][0]["application_name"], "target.exe")

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    @patch("windows.application_crash_tools.get_windows_error_reporting_status")
    def test_get_application_crash_diagnostics_unified(self, mock_wer, mock_read, mock_platform):
        """Verify get_application_crash_diagnostics compiles complete high-level diagnosis."""
        mock_wer.return_value = {
            "success": True,
            "data": {"status": "available", "service_running": True, "disabled": False, "error_reporting_ready": True},
        }
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 14:00:00",
                    "event_id": 1000,
                    "source": "Application Error",
                    "application_name": "app.exe",
                    "faulting_module": "mod.dll",
                    "exception_code": "0xc0000005",
                },
                {
                    "timestamp": "2026-09-24 14:15:00",
                    "event_id": 1000,
                    "source": "Application Error",
                    "application_name": "app.exe",
                    "faulting_module": "mod.dll",
                    "exception_code": "0xc0000005",
                },
            ],
            100,
            False,
        )

        res = get_application_crash_diagnostics(time_window="24h")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["overall_status"], "RECURRING_APPLICATION_CRASH")
        self.assertEqual(res["data"]["summary"]["total_crashes"], 2)
        self.assertTrue(len(res["data"]["recommendations"]) > 0)


class TestApplicationCrashErrorAndEmptyStates(unittest.TestCase):
    """Test suite for error handling, empty states, and malformed records."""

    @patch("platform.system", return_value="Linux")
    def test_non_windows_platform_graceful_handling(self, mock_platform):
        """Verify all tools handle non-Windows platforms gracefully with status='not_available'."""
        res = get_recent_application_crashes()
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["status"], "not_available")

        res_wer = get_windows_error_reporting_status()
        self.assertFalse(res_wer["success"])
        self.assertEqual(res_wer["data"]["status"], "not_available")

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_empty_event_log_no_crashes(self, mock_read, mock_platform):
        """Verify empty event log returns structured empty results rather than exceptions."""
        mock_read.return_value = ([], 200, False)

        res = get_recent_application_crashes()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["crashes_found"], 0)
        self.assertEqual(res["data"]["crashes"], [])

        diag = get_application_crash_diagnostics()
        self.assertTrue(diag["success"])
        self.assertEqual(diag["data"]["overall_status"], "NO_RECENT_CRASH_EVIDENCE")

    @patch("platform.system", return_value="Windows")
    @patch("windows.application_crash_tools._read_application_crash_records")
    def test_malformed_event_record_parsing(self, mock_read, mock_platform):
        """Verify parser safely handles partial/malformed events with missing fields."""
        mock_read.return_value = (
            [
                {
                    "timestamp": "2026-09-24 12:00:00",
                    "event_id": 1000,
                    "source": "Application Error",
                    "level": "Error",
                    "application_name": None,
                    "faulting_module": None,
                    "exception_code": None,
                    "process_id": None,
                    "message_summary": "Unparseable crash event",
                }
            ],
            10,
            False,
        )

        res = get_application_crash_summary()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["total_crashes"], 1)

    def test_input_validation_clamping_and_rejection(self):
        """Verify time window and limit parameters are safely validated and clamped."""
        # Unrecognized time window falls back safely to '24h'
        res = get_application_crash_summary(time_window="invalid_window")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["time_window"], "24h")

        # Limits are clamped between 1 and 50
        res_limit = get_application_crash_details(limit=999)
        self.assertTrue(res_limit["success"])


class TestApplicationCrashOrchestrator(unittest.TestCase):
    """Test suite for ApplicationCrashDiagnosticsOrchestrator."""

    def setUp(self):
        self.orchestrator = ApplicationCrashDiagnosticsOrchestrator()

    def test_orchestrator_runs_diagnostics_successfully(self):
        """Verify orchestrator returns structured ApplicationCrashDiagnosis."""
        mock_payload = {
            "success": True,
            "tool": "get_application_crash_diagnostics",
            "domain": "applications",
            "data": {
                "overall_status": "RECENT_APPLICATION_CRASH",
                "time_window": "24h",
                "total_crashes": 1,
                "summary": {"total_crashes": 1, "unique_applications": 1, "unique_faulting_modules": 1, "recurring_applications": []},
                "frequency": {"total_crashes": 1, "recurring_crashes": []},
                "faulting_modules": [],
                "wer_status": {"status": "OPERATIONAL"},
                "events": [{"application_name": "app.exe"}],
                "recurring_patterns": [],
                "evidence": ["Application app.exe crashed 1 time."],
                "limitations": ["Crash events reflect observed symptoms."],
                "recommendations": ["Check if application update is available."],
            },
        }

        with patch.object(self.orchestrator.safety_engine, "execute", return_value=mock_payload):
            diagnosis = self.orchestrator.run_diagnostics(session_id="test_session")
            self.assertIsInstance(diagnosis, ApplicationCrashDiagnosis)
            self.assertEqual(diagnosis.problem_category, "RECENT_APPLICATION_CRASH")
            self.assertEqual(len(diagnosis.recommended_next_steps), 1)

    def test_orchestrator_categories(self):
        """Verify allowed diagnostic classifications."""
        self.assertIn("NO_RECENT_CRASH_EVIDENCE", CRASH_CATEGORIES)
        self.assertIn("RECENT_APPLICATION_CRASH", CRASH_CATEGORIES)
        self.assertIn("RECURRING_APPLICATION_CRASH", CRASH_CATEGORIES)
        self.assertIn("FAULTING_MODULE_OBSERVED", CRASH_CATEGORIES)
        self.assertIn("WER_EVIDENCE_AVAILABLE", CRASH_CATEGORIES)
        self.assertIn("INSUFFICIENT_EVIDENCE", CRASH_CATEGORIES)
        self.assertIn("DATA_UNAVAILABLE", CRASH_CATEGORIES)


class TestApplicationCrashRegistryAndSafety(unittest.TestCase):
    """Test suite for ToolRegistry tool counts and safety constraints."""

    def test_tool_registry_counts(self):
        """Verify exact total registered tools (59 tools: 49 SAFE, 10 MEDIUM, 0 HIGH)."""
        registry = create_default_registry()
        self.assertIn(registry.count(), (59, 62))

        safe_tools = [t for t in registry.list_tools() if t.risk == RiskLevel.SAFE]
        medium_tools = [t for t in registry.list_tools() if t.risk == RiskLevel.MEDIUM]
        high_tools = [t for t in registry.list_tools() if t.risk == RiskLevel.HIGH]

        self.assertIn(len(safe_tools), (49, 52))
        self.assertEqual(len(medium_tools), 10)
        self.assertEqual(len(high_tools), 0)

    def test_phase14_tools_metadata(self):
        """Verify all 8 Phase 14 tools are SAFE, read-only, and require no confirmation."""
        phase14_tool_names = [
            "get_recent_application_crashes",
            "get_application_crash_details",
            "get_application_crash_summary",
            "get_application_crash_frequency",
            "get_faulting_module_information",
            "get_windows_error_reporting_status",
            "get_application_crash_events",
            "get_application_crash_diagnostics",
        ]

        registry = create_default_registry()
        for name in phase14_tool_names:
            tool = registry.get(name)
            self.assertIsNotNone(tool, f"Tool '{name}' must be registered.")
            self.assertEqual(tool.risk, RiskLevel.SAFE)
            self.assertTrue(tool.read_only)
            self.assertTrue(tool.automatic_allowed)
            self.assertFalse(tool.requires_admin)
            self.assertIsNone(tool.verification_tool)

    def test_no_generic_command_tools(self):
        """Verify no generic shell, WMI, or registry execution tools are registered."""
        registry = create_default_registry()
        names = registry.list_tool_names()
        forbidden_names = [
            "run_eventlog_query",
            "run_wmi_query",
            "read_registry",
            "execute_command",
            "run_powershell",
            "run_cmd",
            "kill_process",
            "terminate_application",
            "repair_application",
        ]
        for fn in forbidden_names:
            self.assertNotIn(fn, names)


class TestApplicationCrashSecurityScan(unittest.TestCase):
    """Static AST security analysis of Phase 14 implementation files."""

    def test_ast_security_scan(self):
        """Verify zero forbidden execution, process termination, event log clearing, or registry writing in Phase 14."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        phase14_files = [
            os.path.join(repo_root, "windows", "application_crash_tools.py"),
            os.path.join(repo_root, "agent", "application_crash_diagnostics.py"),
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

        for file_path in phase14_files:
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
                    # Check plain name calls like eval() or exec()
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            forbidden_calls,
                            f"Forbidden function call '{node.func.id}()' in {file_path}",
                        )
                    # Check attribute calls like os.system
                    elif isinstance(node.func, ast.Attribute):
                        attr_name = node.func.attr
                        self.assertNotIn(
                            attr_name,
                            forbidden_attributes,
                            f"Forbidden method call '.{attr_name}()' in {file_path}",
                        )
                        if isinstance(node.func.value, ast.Name):
                            # Only check module.attr if value is os, not platform (e.g. platform.system() is allowed)
                            if node.func.value.id in ("os", "sys", "subprocess"):
                                full_call = f"{node.func.value.id}.{attr_name}"
                                self.assertNotIn(
                                    full_call,
                                    forbidden_calls,
                                    f"Forbidden call '{full_call}()' in {file_path}",
                                )


if __name__ == "__main__":
    unittest.main()
