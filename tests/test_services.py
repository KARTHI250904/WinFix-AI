"""Unit Tests for Windows Services Diagnostics & Controlled Repairs (Phase 10).

Covers:
1. Service status & startup type normalization
2. Service name validation & sanitization
3. Read-only service diagnostics & details inspection
4. Protected service policy verification
5. ToolRegistry registration & safety risk classification (SAFE vs MEDIUM)
6. Cryptographic SHA-256 confirmation token binding & tamper detection
7. Controlled service repair execution (start, stop, restart) with before/after state verification
8. Service diagnostics orchestrator scenarios (stopped, disabled, running, general)
9. AST static security audit ensuring zero shell/subprocess/command strings
"""

import ast
import os
import unittest
from unittest.mock import MagicMock, patch

from agent.safety import SafetyEngine
from agent.service_diagnostics import (
    KEYWORD_SERVICE_MAP,
    ServiceDiagnosis,
    ServiceDiagnosticsOrchestrator,
)
from agent.service_repairs_orchestrator import (
    ServiceRepairExecutionResult,
    ServiceRepairProposal,
    ServiceRepairsOrchestrator,
)
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from database.db import DatabaseManager
from windows.service_repairs import (
    PROTECTED_SERVICES,
    is_service_stop_protected,
    restart_service,
    start_service,
    stop_service,
)
from windows.service_tools import (
    get_service_details,
    get_service_status,
    get_services_diagnostics,
    list_common_services,
    normalize_service_status,
    normalize_startup_type,
    validate_service_name,
)


class TestServiceDiagnosticsNormalization(unittest.TestCase):
    """Test suite for service status and startup type normalization."""

    def test_normalize_service_status(self) -> None:
        self.assertEqual(normalize_service_status("running"), "RUNNING")
        self.assertEqual(normalize_service_status("stopped"), "STOPPED")
        self.assertEqual(normalize_service_status("start_pending"), "START_PENDING")
        self.assertEqual(normalize_service_status("stop_pending"), "STOP_PENDING")
        self.assertEqual(normalize_service_status("paused"), "PAUSED")
        self.assertEqual(normalize_service_status("pause_pending"), "PAUSE_PENDING")
        self.assertEqual(normalize_service_status("continue_pending"), "CONTINUE_PENDING")
        self.assertEqual(normalize_service_status(""), "UNKNOWN")
        self.assertEqual(normalize_service_status(None), "UNKNOWN")
        self.assertEqual(normalize_service_status("CUSTOM_STATUS"), "CUSTOM_STATUS")

    def test_normalize_startup_type(self) -> None:
        self.assertEqual(normalize_startup_type("automatic"), "AUTO")
        self.assertEqual(normalize_startup_type("auto"), "AUTO")
        self.assertEqual(normalize_startup_type("manual"), "DEMAND")
        self.assertEqual(normalize_startup_type("demand"), "DEMAND")
        self.assertEqual(normalize_startup_type("disabled"), "DISABLED")
        self.assertEqual(normalize_startup_type("boot"), "BOOT")
        self.assertEqual(normalize_startup_type("system"), "SYSTEM")
        self.assertEqual(normalize_startup_type(""), "UNKNOWN")
        self.assertEqual(normalize_startup_type(None), "UNKNOWN")


class TestServiceNameValidation(unittest.TestCase):
    """Test suite for strict service name validation and sanitization."""

    def test_valid_service_names(self) -> None:
        valid_names = ["Spooler", "wuauserv", "Dhcp", "bthserv", "WinDefend", "Service_1", "my.service-test"]
        for name in valid_names:
            valid, clean, err = validate_service_name(name)
            self.assertTrue(valid, f"Expected '{name}' to be valid.")
            self.assertEqual(clean, name)
            self.assertIsNone(err)

    def test_invalid_service_names(self) -> None:
        invalid_cases = [
            ("", "empty"),
            ("   ", "whitespace"),
            (None, "none"),
            ("Spooler & whoami", "command separator &"),
            ("Spooler; powershell", "command separator ;"),
            ("Spooler | net stop", "pipe |"),
            ("Spooler`dir`", "backtick"),
            ("$SERVICE", "dollar sign"),
            ("Spooler\nmalicious", "newline"),
            ("Spooler\rmalicious", "carriage return"),
            ("C:\\Windows\\System32\\svc.exe", "path backslash"),
            ("/usr/bin/service", "path slash"),
            ("svc:test", "colon"),
            ("..\\service", "dot dot traversal"),
            ('service"name', "quotes"),
            ("A" * 150, "excessive length"),
        ]
        for name, reason in invalid_cases:
            valid, _, err = validate_service_name(name)
            self.assertFalse(valid, f"Expected '{name}' ({reason}) to be rejected.")
            self.assertIsNotNone(err)


class TestServiceDiagnosticsTools(unittest.TestCase):
    """Test suite for read-only Windows service diagnostic tools."""

    @patch("windows.service_tools.psutil.win_service_get")
    def test_get_service_status_success(self, mock_get: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.as_dict.return_value = {
            "name": "Spooler",
            "display_name": "Print Spooler",
            "status": "running",
            "start_type": "automatic",
            "pid": 1234,
        }
        mock_get.return_value = mock_svc

        res = get_service_status("Spooler")
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_service_status")
        self.assertEqual(res["data"]["status"], "RUNNING")
        self.assertEqual(res["data"]["start_type"], "AUTO")
        self.assertTrue(res["data"]["is_running"])

    @patch("windows.service_tools.psutil.win_service_get")
    def test_get_service_status_not_found(self, mock_get: MagicMock) -> None:
        import psutil
        mock_get.side_effect = psutil.NoSuchProcess(pid=0, name="NonexistentService")

        res = get_service_status("NonexistentService")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "SERVICE_NOT_FOUND")

    @patch("windows.service_tools.psutil.win_service_get")
    def test_get_service_details_success(self, mock_get: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.as_dict.return_value = {
            "name": "wuauserv",
            "display_name": "Windows Update",
            "status": "running",
            "start_type": "manual",
            "username": "LocalSystem",
            "binpath": "C:\\Windows\\system32\\svchost.exe -k netsvcs -p",
            "pid": 2345,
        }
        mock_svc.description.return_value = "Enables the detection, download, and installation of updates for Windows."
        mock_get.return_value = mock_svc

        res = get_service_details("wuauserv")
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_service_details")
        self.assertEqual(res["data"]["name"], "wuauserv")
        self.assertEqual(res["data"]["status"], "RUNNING")
        self.assertEqual(res["data"]["start_type"], "DEMAND")
        self.assertEqual(res["data"]["account"], "LocalSystem")
        self.assertIn("Enables the detection", res["data"]["description"])

    @patch("windows.service_tools.psutil.win_service_iter")
    def test_get_services_diagnostics_bounded(self, mock_iter: MagicMock) -> None:
        mock_services = []
        for i in range(10):
            mock_s = MagicMock()
            mock_s.as_dict.return_value = {
                "name": f"Service_{i}",
                "display_name": f"Display Service {i}",
                "status": "running" if i % 2 == 0 else "stopped",
                "start_type": "automatic",
                "pid": 1000 + i if i % 2 == 0 else None,
            }
            mock_services.append(mock_s)
        mock_iter.return_value = mock_services

        res = get_services_diagnostics(limit=5)
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_services_diagnostics")
        self.assertEqual(len(res["data"]["services"]), 5)
        self.assertEqual(res["data"]["total_running"], 5)
        self.assertEqual(res["data"]["total_stopped"], 5)

    @patch("windows.service_tools.get_service_status")
    def test_list_common_services(self, mock_status: MagicMock) -> None:
        mock_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "domain": "services",
            "data": {
                "name": "Spooler",
                "display_name": "Print Spooler",
                "status": "RUNNING",
                "start_type": "AUTO",
                "is_running": True,
                "pid": 1234,
            },
            "error": None,
        }
        res = list_common_services()
        self.assertTrue(res["success"])
        self.assertGreater(res["data"]["total_monitored"], 0)


class TestProtectedServicesPolicy(unittest.TestCase):
    """Test suite for critical Windows service protection policy."""

    def test_critical_services_are_protected(self) -> None:
        critical_list = [
            "WinDefend",
            "WdNisSvc",
            "MpsSvc",
            "BFE",
            "EventLog",
            "RpcSs",
            "RpcEptMapper",
            "DcomLaunch",
            "PlugPlay",
            "LSM",
            "SamSs",
            "ProfSvc",
            "Schedule",
            "Winmgmt",
            "CryptSvc",
            "BITS",
            "wuauserv",
            "Dhcp",
            "Dnscache",
            "wscsvc",
            "SecurityHealthService",
            "Appinfo",
        ]
        for s in critical_list:
            is_prot, reason = is_service_stop_protected(s)
            self.assertTrue(is_prot, f"Service '{s}' must be protected from stopping.")
            self.assertIn("critical", reason.lower())

    def test_non_critical_service_is_not_protected(self) -> None:
        non_critical = ["Spooler", "bthserv", "W32Time", "CustomWorkerSvc"]
        for s in non_critical:
            is_prot, reason = is_service_stop_protected(s)
            self.assertFalse(is_prot, f"Service '{s}' should not be blocked by protected list.")


class TestToolRegistryPhase10(unittest.TestCase):
    """Test suite verifying ToolRegistry tool definitions and safety metadata."""

    def setUp(self) -> None:
        self.registry = create_default_registry()

    def test_registered_tool_count(self) -> None:
        # Verify all service tools are included in registered catalog
        self.assertGreaterEqual(self.registry.count(), 32)


    def test_phase10_diagnostic_tools_metadata(self) -> None:
        diag_tools = ["get_services_diagnostics", "get_service_details", "get_service_status", "list_common_services"]
        for t_name in diag_tools:
            tool = self.registry.get(t_name)
            self.assertIsNotNone(tool, f"Tool '{t_name}' must be registered.")
            self.assertEqual(tool.risk, RiskLevel.SAFE)
            self.assertTrue(tool.read_only)
            self.assertTrue(tool.automatic_allowed)
            self.assertFalse(tool.requires_admin)

    def test_phase10_repair_tools_metadata(self) -> None:
        repair_tools = ["start_service", "stop_service", "restart_service"]
        for t_name in repair_tools:
            tool = self.registry.get(t_name)
            self.assertIsNotNone(tool, f"Repair tool '{t_name}' must be registered.")
            self.assertEqual(tool.risk, RiskLevel.MEDIUM)
            self.assertFalse(tool.read_only)
            self.assertFalse(tool.automatic_allowed)
            self.assertTrue(tool.requires_admin)
            self.assertEqual(tool.verification_tool, "get_service_status")


class TestServiceRepairsControlledExecution(unittest.TestCase):
    """Test suite for controlled Windows service repair operations with deterministic verification."""

    @patch("windows.service_repairs.get_service_status")
    @patch("win32serviceutil.StartService", create=True)
    def test_start_service_success(self, mock_start: MagicMock, mock_status: MagicMock) -> None:
        mock_status.side_effect = [
            # Before-state
            {
                "success": True,
                "tool": "get_service_status",
                "domain": "services",
                "data": {"name": "Spooler", "display_name": "Print Spooler", "status": "STOPPED", "start_type": "AUTO", "is_running": False},
                "error": None,
            },
            # Poll status after start
            {
                "success": True,
                "tool": "get_service_status",
                "domain": "services",
                "data": {"name": "Spooler", "display_name": "Print Spooler", "status": "RUNNING", "start_type": "AUTO", "is_running": True},
                "error": None,
            },
        ]

        res = start_service("Spooler")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["before_state"], "STOPPED")
        self.assertEqual(res["data"]["after_state"], "RUNNING")
        self.assertEqual(res["data"]["verification"], "verified")

    @patch("windows.service_repairs.get_service_status")
    def test_start_service_already_running(self, mock_status: MagicMock) -> None:
        mock_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "domain": "services",
            "data": {"name": "Spooler", "display_name": "Print Spooler", "status": "RUNNING", "start_type": "AUTO", "is_running": True},
            "error": None,
        }
        res = start_service("Spooler")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["verification"], "verified")
        self.assertEqual(res["data"]["after_state"], "RUNNING")

    @patch("windows.service_repairs.get_service_status")
    def test_start_service_disabled_blocked(self, mock_status: MagicMock) -> None:
        mock_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "domain": "services",
            "data": {"name": "Spooler", "display_name": "Print Spooler", "status": "STOPPED", "start_type": "DISABLED", "is_running": False},
            "error": None,
        }
        res = start_service("Spooler")
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["verification"], "blocked")
        self.assertEqual(res["error"]["code"], "SERVICE_DISABLED")

    @patch("windows.service_repairs.get_service_status")
    @patch("win32serviceutil.StopService", create=True)
    def test_stop_service_success(self, mock_stop: MagicMock, mock_status: MagicMock) -> None:
        mock_status.side_effect = [
            # Before-state
            {
                "success": True,
                "tool": "get_service_status",
                "domain": "services",
                "data": {"name": "Spooler", "display_name": "Print Spooler", "status": "RUNNING", "start_type": "DEMAND", "is_running": True},
                "error": None,
            },
            # Poll status after stop
            {
                "success": True,
                "tool": "get_service_status",
                "domain": "services",
                "data": {"name": "Spooler", "display_name": "Print Spooler", "status": "STOPPED", "start_type": "DEMAND", "is_running": False},
                "error": None,
            },
        ]
        res = stop_service("Spooler")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["before_state"], "RUNNING")
        self.assertEqual(res["data"]["after_state"], "STOPPED")
        self.assertEqual(res["data"]["verification"], "verified")

    def test_stop_service_protected_blocked(self) -> None:
        res = stop_service("WinDefend")
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["verification"], "blocked")
        self.assertEqual(res["error"]["code"], "PROTECTED_SERVICE_BLOCKED")

    def test_restart_service_protected_blocked(self) -> None:
        res = restart_service("wuauserv")
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["verification"], "blocked")
        self.assertEqual(res["error"]["code"], "PROTECTED_SERVICE_BLOCKED")


class TestConfirmationTokenAndOrchestrator(unittest.TestCase):
    """Test suite for cryptographic confirmation token binding, tamper resistance, and orchestrator execution."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_services.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db.init_db()
        self.safety_engine = SafetyEngine()
        self.orchestrator = ServiceRepairsOrchestrator(
            safety_engine=self.safety_engine,
            db_mgr=self.db,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()



    def test_confirmation_token_binding(self) -> None:
        proposal = ServiceRepairProposal(
            tool_name="start_service",
            arguments={"service_name": "Spooler"},
            service_name="Spooler",
        )
        token = proposal.generate_confirmation_token(session_id="session-100")
        self.assertTrue(self.orchestrator.validate_confirmation_token(token, "start_service", {"service_name": "Spooler"}, "session-100"))

    def test_confirmation_token_tamper_detection(self) -> None:
        proposal = ServiceRepairProposal(
            tool_name="start_service",
            arguments={"service_name": "Spooler"},
            service_name="Spooler",
        )
        token = proposal.generate_confirmation_token(session_id="session-100")

        # Wrong service argument
        self.assertFalse(self.orchestrator.validate_confirmation_token(token, "start_service", {"service_name": "WinDefend"}, "session-100"))
        # Wrong tool name
        self.assertFalse(self.orchestrator.validate_confirmation_token(token, "stop_service", {"service_name": "Spooler"}, "session-100"))
        # Wrong session id
        self.assertFalse(self.orchestrator.validate_confirmation_token(token, "start_service", {"service_name": "Spooler"}, "session-999"))

    @patch("agent.safety.SafetyEngine.execute")
    def test_execute_confirmed_repair_success(self, mock_exec: MagicMock) -> None:
        from database.repositories import SessionRepository
        SessionRepository(self.db).create(session_id="sess-1")

        # Mock responses for before query, repair action, and after query
        mock_exec.side_effect = [
            # Before get_service_status
            {"success": True, "data": {"name": "Spooler", "status": "STOPPED"}},
            # start_service repair
            {"success": True, "data": {"service_name": "Spooler", "operation": "start", "after_state": "RUNNING"}},
            # After get_service_status
            {"success": True, "data": {"name": "Spooler", "status": "RUNNING"}},
        ]


        token = ServiceRepairProposal(
            tool_name="start_service",
            arguments={"service_name": "Spooler"},
            service_name="Spooler",
        ).generate_confirmation_token("sess-1")

        res = self.orchestrator.execute_confirmed_repair(
            tool_name="start_service",
            arguments={"service_name": "Spooler"},
            confirmation_token=token,
            session_id="sess-1",
        )

        self.assertTrue(res.confirmed)
        self.assertTrue(res.repair_success)
        self.assertEqual(res.verification_status, "verified")
        self.assertEqual(res.before_state.get("status"), "STOPPED")
        self.assertEqual(res.after_state.get("status"), "RUNNING")


class TestServiceDiagnosticsScenarios(unittest.TestCase):
    """Test suite for ServiceDiagnosticsOrchestrator scenarios (stopped, disabled, running, general)."""

    def setUp(self) -> None:
        self.safety_engine = SafetyEngine()
        self.diag_orchestrator = ServiceDiagnosticsOrchestrator(safety_engine=self.safety_engine)

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_service_stopped(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "name": "Spooler",
                "display_name": "Print Spooler",
                "status": "STOPPED",
                "start_type": "AUTO",
                "description": "Spooler service",
            },
        }
        diagnosis = self.diag_orchestrator.diagnose_service("Spooler")
        self.assertEqual(diagnosis.problem_category, "service_stopped")
        self.assertTrue(diagnosis.repair_available)
        self.assertEqual(diagnosis.proposed_tool, "start_service")
        self.assertEqual(diagnosis.target_service, "Spooler")

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_service_disabled(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "name": "Spooler",
                "display_name": "Print Spooler",
                "status": "STOPPED",
                "start_type": "DISABLED",
                "description": "Spooler service",
            },
        }
        diagnosis = self.diag_orchestrator.diagnose_service("Spooler")
        self.assertEqual(diagnosis.problem_category, "service_disabled")
        self.assertFalse(diagnosis.repair_available)

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_service_running(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "name": "Spooler",
                "display_name": "Print Spooler",
                "status": "RUNNING",
                "start_type": "AUTO",
                "description": "Spooler service",
            },
        }
        diagnosis = self.diag_orchestrator.diagnose_service("Spooler")
        self.assertEqual(diagnosis.problem_category, "service_running")
        self.assertFalse(diagnosis.repair_available)


class TestASTStaticSecurityAudit(unittest.TestCase):
    """AST static security scanner ensuring absolute compliance with LLM != Windows Shell."""

    def test_zero_forbidden_abstractions_in_phase10_code(self) -> None:
        forbidden_calls = {"subprocess", "os.system", "os.popen", "eval", "exec"}
        forbidden_strings = [
            "sc.exe",
            "cmd.exe",
            "powershell.exe",
            "pwsh.exe",
            "net.exe",
            "taskkill",
            "TerminateProcess",
        ]

        files_to_scan = [
            "windows/service_tools.py",
            "windows/service_repairs.py",
            "agent/service_diagnostics.py",
            "agent/service_repairs_orchestrator.py",
        ]

        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for rel_path in files_to_scan:
            full_path = os.path.join(workspace_root, rel_path)
            self.assertTrue(os.path.exists(full_path), f"File {full_path} must exist.")

            with open(full_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=rel_path)

            for node in ast.walk(tree):
                # Check for forbidden calls (eval, exec)
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                        self.fail(f"Forbidden call '{node.func.id}' found in {rel_path} at line {node.lineno}")
                    elif isinstance(node.func, ast.Attribute):
                        attr_name = node.func.attr
                        # Match os.system, os.popen, subprocess.*
                        if isinstance(node.func.value, ast.Name):
                            val_id = node.func.value.id
                            if val_id == "os" and attr_name in {"system", "popen"}:
                                self.fail(f"Forbidden call 'os.{attr_name}' found in {rel_path} at line {node.lineno}")
                            elif val_id == "subprocess":
                                self.fail(f"Forbidden call 'subprocess.{attr_name}' found in {rel_path} at line {node.lineno}")

                # Check for shell=True
                if isinstance(node, ast.keyword) and node.arg == "shell":
                    if isinstance(node.value, ast.Constant) and node.value.value is True:
                        self.fail(f"Forbidden 'shell=True' found in {rel_path} at line {node.lineno}")

            # Check for forbidden executable strings in non-comment/non-docstring code
            for s in forbidden_strings:
                # Disallow forbidden commands in actual execution logic
                self.assertNotIn(f'"{s}"', source, f"Forbidden string '\"{s}\"' found in {rel_path}")
                self.assertNotIn(f"'{s}'", source, f"Forbidden string \"'{s}'\" found in {rel_path}")



if __name__ == "__main__":
    unittest.main()
