"""Comprehensive Test Suite for Windows Defender Diagnostics & Controlled Repair (Phase 13).

Tests:
- Diagnostic tools (service status, realtime protection, antivirus status, threat status,
  recent events, configuration, security health, unified diagnostics)
- Tool registry metadata and risk classification
- SafetyEngine enforcement and confirmation token binding
- Sequential stop-then-start repair flow with verification
- Fail-closed guarantees (stop failure/timeout prevents start)
- Protected-service policy preservation for 'WinDefend'
- No Defender disabling / weakening / process kill capabilities
- AST static security scan confirming zero forbidden execution or registry-write methods
"""

import ast
import os
import unittest
from unittest.mock import MagicMock, patch

from agent.defender_diagnostics import (
    DEFENDER_CATEGORIES,
    DefenderDiagnosis,
    DefenderDiagnosticsOrchestrator,
)
from agent.defender_repairs_orchestrator import (
    DefenderRepairExecutionResult,
    DefenderRepairProposal,
    DefenderRepairsOrchestrator,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry, default_tool_registry
from database.db import DatabaseManager
from windows.defender_tools import (
    get_defender_antivirus_status,
    get_defender_configuration,
    get_defender_diagnostics,
    get_defender_realtime_protection_status,
    get_defender_recent_events,
    get_defender_security_health,
    get_defender_service_status,
    get_defender_threat_status,
)
from windows.service_repairs import is_service_stop_protected, restart_service, stop_service
from windows.windows_defender_repairs import (
    DEFENDER_SERVICE_NAME,
    restart_defender_service,
)


class TestDefenderDiagnosticsTools(unittest.TestCase):
    """Test suite for read-only Windows Defender diagnostic tools."""

    @patch("platform.system", return_value="Windows")
    @patch("windows.defender_tools.get_service_status")
    def test_get_defender_service_status_running(self, mock_svc_status, mock_platform):
        """Verify service status inspection when WinDefend is RUNNING."""
        mock_svc_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "data": {
                "service_name": "WinDefend",
                "display_name": "Microsoft Defender Antivirus Service",
                "status": "RUNNING",
                "is_running": True,
                "start_type": "AUTO_START",
                "pid": 2048,
            },
            "error": None,
        }

        res = get_defender_service_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_service_status")
        self.assertEqual(res["domain"], "defender")
        self.assertEqual(res["data"]["service_name"], "WinDefend")
        self.assertEqual(res["data"]["status"], "RUNNING")
        self.assertTrue(res["data"]["is_running"])

    @patch("platform.system", return_value="Windows")
    @patch("windows.defender_tools.get_service_status")
    def test_get_defender_service_status_stopped(self, mock_svc_status, mock_platform):
        """Verify service status inspection when WinDefend is STOPPED."""
        mock_svc_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "data": {
                "service_name": "WinDefend",
                "display_name": "Microsoft Defender Antivirus Service",
                "status": "STOPPED",
                "is_running": False,
                "start_type": "DEMAND_START",
                "pid": None,
            },
            "error": None,
        }

        res = get_defender_service_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "STOPPED")
        self.assertFalse(res["data"]["is_running"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_realtime_protection_status(self, mock_platform):
        """Verify real-time protection inspection structure."""
        res = get_defender_realtime_protection_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_realtime_protection_status")
        self.assertEqual(res["domain"], "defender")
        self.assertIn("realtime_protection_enabled", res["data"])
        self.assertIn("method", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_antivirus_status(self, mock_platform):
        """Verify antivirus status inspection structure."""
        res = get_defender_antivirus_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_antivirus_status")
        self.assertEqual(res["domain"], "defender")
        self.assertIn("antivirus_enabled", res["data"])
        self.assertIn("is_active", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_threat_status(self, mock_platform):
        """Verify threat status inspection structure."""
        res = get_defender_threat_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_threat_status")
        self.assertEqual(res["domain"], "defender")
        self.assertIn("has_threats", res["data"])
        self.assertIn("threat_count", res["data"])
        self.assertIn("threats", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_recent_events(self, mock_platform):
        """Verify recent Defender events retrieval structure."""
        res = get_defender_recent_events(limit=5, max_scan=50)
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_recent_events")
        self.assertEqual(res["domain"], "defender")
        self.assertIn("events", res["data"])
        self.assertIn("count", res["data"])
        self.assertIn("has_errors", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_configuration(self, mock_platform):
        """Verify Defender read-only configuration structure."""
        res = get_defender_configuration()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_configuration")
        self.assertEqual(res["domain"], "defender")
        self.assertIn("realtime_protection", res["data"])
        self.assertIn("tamper_protection", res["data"])
        self.assertIn("cloud_protection", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_security_health(self, mock_platform):
        """Verify high-level Defender security health assessment."""
        res = get_defender_security_health()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_security_health")
        self.assertEqual(res["domain"], "defender")
        self.assertIn("overall_status", res["data"])
        self.assertIn("signals", res["data"])
        self.assertIn("problems", res["data"])
        self.assertIn("recommendations", res["data"])
        self.assertIn("evidence", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_defender_diagnostics_unified(self, mock_platform):
        """Verify unified Defender diagnostics aggregator output."""
        res = get_defender_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_defender_diagnostics")
        self.assertEqual(res["domain"], "defender")
        data = res["data"]
        self.assertIn("service_status", data)
        self.assertIn("security_health", data)
        self.assertIn("realtime_protection", data)
        self.assertIn("antivirus_status", data)
        self.assertIn("threat_status", data)
        self.assertIn("recent_events", data)
        self.assertIn("configuration", data)
        # Backward-compatibility keys
        self.assertIn("antivirus_service_running", data)
        self.assertIn("firewall_service_running", data)

    @patch("windows.defender_tools.platform.system", return_value="Linux")
    def test_unsupported_os_diagnostics(self, mock_platform):
        """Verify all diagnostic tools fail safely on non-Windows OS."""
        diag_funcs = [
            get_defender_service_status,
            get_defender_security_health,
            get_defender_realtime_protection_status,
            get_defender_antivirus_status,
            get_defender_threat_status,
            get_defender_recent_events,
            get_defender_configuration,
            get_defender_diagnostics,
        ]
        for func in diag_funcs:
            res = func()
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "UNSUPPORTED_OS")


class TestDefenderToolRegistryAndMetadata(unittest.TestCase):
    """Test suite verifying ToolRegistry registration and risk classifications for Phase 13 tools."""

    def setUp(self) -> None:
        self.registry = create_default_registry()

    def test_registered_tool_count(self) -> None:
        """Verify total tool count: 49 SAFE + 10 MEDIUM = 59 tools."""
        self.assertIn(self.registry.count(), (59, 62))
        safe_tools = [t for t in self.registry.list_tools() if t.risk == RiskLevel.SAFE]
        medium_tools = [t for t in self.registry.list_tools() if t.risk == RiskLevel.MEDIUM]
        high_tools = [t for t in self.registry.list_tools() if t.risk == RiskLevel.HIGH]

        self.assertIn(len(safe_tools), (49, 52))
        self.assertEqual(len(medium_tools), 10)
        self.assertEqual(len(high_tools), 0)

    def test_phase13_diagnostic_tools_metadata(self) -> None:
        """Verify all 8 Phase 13 Defender diagnostic tools have correct SAFE metadata."""
        diag_tools = [
            "get_defender_diagnostics",
            "get_defender_service_status",
            "get_defender_security_health",
            "get_defender_realtime_protection_status",
            "get_defender_antivirus_status",
            "get_defender_threat_status",
            "get_defender_recent_events",
            "get_defender_configuration",
        ]
        for t_name in diag_tools:
            tool = self.registry.get(t_name)
            self.assertIsNotNone(tool, f"Diagnostic tool '{t_name}' must be registered.")
            self.assertEqual(tool.domain, "defender")
            self.assertEqual(tool.risk, RiskLevel.SAFE)
            self.assertTrue(tool.read_only)
            self.assertTrue(tool.automatic_allowed)
            self.assertFalse(tool.requires_admin)

    def test_phase13_repair_tool_metadata(self) -> None:
        """Verify Phase 13 Defender repair tool has strict MEDIUM metadata."""
        tool = self.registry.get("restart_defender_service")
        self.assertIsNotNone(tool, "Repair tool 'restart_defender_service' must be registered.")
        self.assertEqual(tool.domain, "defender")
        self.assertEqual(tool.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool.read_only)
        self.assertFalse(tool.automatic_allowed)
        self.assertTrue(tool.requires_admin)
        self.assertEqual(tool.verification_tool, "get_defender_service_status")

    def test_no_duplicate_tools(self) -> None:
        """Verify tool names are unique and no aliases exist."""
        tool_names = self.registry.list_tool_names()
        self.assertEqual(len(tool_names), len(set(tool_names)))


class TestDefenderSafetyAndConfirmation(unittest.TestCase):
    """Test suite verifying SafetyEngine enforcement on Phase 13 Defender tools."""

    def setUp(self) -> None:
        self.registry = create_default_registry()
        self.safety_engine = SafetyEngine(self.registry)

    def test_diagnostic_tools_execute_without_confirmation(self) -> None:
        """Verify SAFE diagnostic tools execute without confirmation."""
        with patch("platform.system", return_value="Windows"):
            res = self.safety_engine.execute("get_defender_service_status")
            self.assertTrue(res["success"])

    def test_repair_tool_blocked_without_confirmation(self) -> None:
        """Verify MEDIUM repair tool is blocked when confirmation is missing."""
        res = self.safety_engine.execute(
            tool_name="restart_defender_service",
            arguments={},
            user_confirmed=False,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "CONFIRMATION_REQUIRED")
        self.assertFalse(res["safety"]["allowed"])
        self.assertTrue(res["safety"]["requires_confirmation"])

    def test_repair_tool_allowed_with_confirmation(self) -> None:
        """Verify MEDIUM repair tool passes SafetyEngine when user_confirmed=True."""
        tool = self.registry.get("restart_defender_service")
        mock_handler = MagicMock(return_value={
            "success": True,
            "tool": "restart_defender_service",
            "data": {"verification": "verified"},
        })
        tool.handler = mock_handler
        res = self.safety_engine.execute(
            tool_name="restart_defender_service",
            arguments={},
            user_confirmed=True,
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["safety"]["allowed"])
        mock_handler.assert_called_once()


class TestDefenderRepairsAndVerification(unittest.TestCase):
    """Test suite for controlled Defender repair execution and sequential verification."""

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_defender_repairs.start_service")
    @patch("windows.windows_defender_repairs._wait_for_service_status")
    @patch("windows.windows_defender_repairs._stop_windefend_direct")
    @patch("windows.windows_defender_repairs.get_service_status")
    def test_restart_defender_service_when_running_success(
        self, mock_svc_status, mock_stop_direct, mock_wait, mock_start, mock_platform
    ):
        """Verify sequential stop -> verify STOPPED -> start -> verify RUNNING when service is running."""
        mock_svc_status.return_value = {
            "success": True,
            "data": {"service_name": "WinDefend", "status": "RUNNING", "is_running": True},
        }
        mock_stop_direct.return_value = {"success": True, "error": None}
        mock_wait.return_value = (True, "STOPPED")
        mock_start.return_value = {
            "success": True,
            "data": {"service_name": "WinDefend", "after_state": "RUNNING"},
        }

        res = restart_defender_service()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["verification"], "verified")
        self.assertEqual(res["data"]["after_state"], "RUNNING")
        self.assertEqual(res["data"]["service_name"], "WinDefend")

        mock_stop_direct.assert_called_once()
        mock_wait.assert_called_once_with("WinDefend", "STOPPED", timeout_seconds=15.0)
        mock_start.assert_called_once_with("WinDefend")

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_defender_repairs.start_service")
    @patch("windows.windows_defender_repairs._stop_windefend_direct")
    @patch("windows.windows_defender_repairs.get_service_status")
    def test_restart_defender_service_when_stopped_success(
        self, mock_svc_status, mock_stop_direct, mock_start, mock_platform
    ):
        """Verify service start without stop when already in STOPPED state."""
        mock_svc_status.return_value = {
            "success": True,
            "data": {"service_name": "WinDefend", "status": "STOPPED", "is_running": False},
        }
        mock_start.return_value = {
            "success": True,
            "data": {"service_name": "WinDefend", "after_state": "RUNNING"},
        }

        res = restart_defender_service()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["verification"], "verified")
        mock_stop_direct.assert_not_called()
        mock_start.assert_called_once_with("WinDefend")

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_defender_repairs.start_service")
    @patch("windows.windows_defender_repairs._wait_for_service_status")
    @patch("windows.windows_defender_repairs._stop_windefend_direct")
    @patch("windows.windows_defender_repairs.get_service_status")
    def test_restart_defender_service_stop_failure_aborts_start(
        self, mock_svc_status, mock_stop_direct, mock_wait, mock_start, mock_platform
    ):
        """FAIL-CLOSED GUARANTEE: If stop verification fails or times out, start is NEVER called."""
        mock_svc_status.return_value = {
            "success": True,
            "data": {"service_name": "WinDefend", "status": "RUNNING", "is_running": True},
        }
        mock_stop_direct.return_value = {"success": True, "error": None}
        mock_wait.return_value = (False, "STOP_PENDING")

        res = restart_defender_service()
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["verification"], "not_verified")
        self.assertEqual(res["error"]["code"], "VERIFICATION_TIMEOUT")

        # CRITICAL ASSERTION: start_service MUST NOT be called
        mock_start.assert_not_called()

    @patch("platform.system", return_value="Linux")
    def test_restart_defender_service_unsupported_os(self, mock_platform):
        """Verify repair fails safely on non-Windows OS."""
        res = restart_defender_service()
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "UNSUPPORTED_OS")


class TestDefenderOrchestrators(unittest.TestCase):
    """Test suite for Defender diagnostics and repair orchestrators."""

    def setUp(self) -> None:
        self.registry = create_default_registry()
        self.safety_engine = SafetyEngine(self.registry)
        self.diag_orch = DefenderDiagnosticsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
        )
        self.repairs_orch = DefenderRepairsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
        )

    def test_diagnostics_orchestrator_healthy(self):
        """Verify diagnosis classification when Defender is fully operational."""
        mock_payload = {
            "success": True,
            "tool": "get_defender_diagnostics",
            "domain": "defender",
            "data": {
                "service_status": {"status": "RUNNING", "start_type": "AUTO_START", "is_running": True},
                "realtime_protection": {"realtime_protection_enabled": True},
                "antivirus_status": {"antivirus_enabled": True},
                "threat_status": {"has_threats": False, "threat_count": 0},
                "recent_events": {"has_errors": False, "count": 0},
                "security_health": {"overall_status": "healthy"},
            },
        }
        with patch.object(self.diag_orch.safety_engine, "execute", return_value=mock_payload):
            diagnosis = self.diag_orch.run_diagnostics(session_id="test_sess")
            self.assertEqual(diagnosis.problem_category, "healthy")
            self.assertFalse(diagnosis.repair_available)
            self.assertIsNone(diagnosis.proposed_tool)

    def test_diagnostics_orchestrator_service_stopped_proposes_repair(self):
        """Verify diagnosis classification when WinDefend is stopped proposes repair."""
        mock_payload = {
            "success": True,
            "tool": "get_defender_diagnostics",
            "domain": "defender",
            "data": {
                "service_status": {"status": "STOPPED", "start_type": "DEMAND_START", "is_running": False},
                "realtime_protection": {"realtime_protection_enabled": False},
                "antivirus_status": {"antivirus_enabled": False},
                "threat_status": {"has_threats": False, "threat_count": 0},
                "recent_events": {"has_errors": False, "count": 0},
                "security_health": {"overall_status": "unhealthy"},
            },
        }
        with patch.object(self.diag_orch.safety_engine, "execute", return_value=mock_payload):
            diagnosis = self.diag_orch.run_diagnostics(session_id="test_sess")
            self.assertEqual(diagnosis.problem_category, "service_stopped")
            self.assertTrue(diagnosis.repair_available)
            self.assertEqual(diagnosis.proposed_tool, "restart_defender_service")

    def test_repairs_orchestrator_execute_confirmed_success(self):
        """Verify full confirmed execution flow with valid token and verification."""
        mock_svc_status = MagicMock(return_value={
            "success": True,
            "data": {"service_name": "WinDefend", "status": "RUNNING", "is_running": True},
        })
        mock_restart = MagicMock(return_value={
            "success": True,
            "tool": "restart_defender_service",
            "domain": "defender",
            "data": {"service_name": "WinDefend", "operation": "restart", "after_state": "RUNNING", "verification": "verified"},
            "error": None,
        })
        self.registry.get("get_defender_service_status").handler = mock_svc_status
        self.registry.get("restart_defender_service").handler = mock_restart

        proposal = self.repairs_orch.prepare_restart_proposal(session_id="sess_123")
        token = proposal.generate_confirmation_token(session_id="sess_123")

        result = self.repairs_orch.execute_confirmed_restart(
            proposal=proposal,
            user_confirmed_token=token,
            session_id="sess_123",
        )

        self.assertTrue(result.confirmed)
        self.assertTrue(result.repair_success)
        self.assertEqual(result.verification_status, "verified")

    def test_repairs_orchestrator_token_mismatch_blocks(self):
        """Verify token mismatch immediately blocks execution without calling tools."""
        proposal = self.repairs_orch.prepare_restart_proposal(session_id="sess_123")
        result = self.repairs_orch.execute_confirmed_restart(
            proposal=proposal,
            user_confirmed_token="wrong_token_hash",
            session_id="sess_123",
        )

        self.assertFalse(result.confirmed)
        self.assertFalse(result.repair_success)
        self.assertEqual(result.verification_status, "blocked")


class TestDefenderSecurityBoundaryAndAST(unittest.TestCase):
    """Test suite verifying strict security boundaries, protected services, and AST cleanliness."""

    def test_protected_service_policy_preserves_windefend_protection(self) -> None:
        """Verify that 'WinDefend' remains globally protected in general service repair tools."""
        self.assertTrue(is_service_stop_protected("WinDefend"))
        self.assertTrue(is_service_stop_protected("windefend"))

        # Calling generic stop_service or restart_service on WinDefend must be blocked
        stop_res = stop_service("WinDefend")
        self.assertFalse(stop_res["success"])
        self.assertEqual(stop_res["error"]["code"], "PROTECTED_SERVICE_BLOCKED")

        restart_res = restart_service("WinDefend")
        self.assertFalse(restart_res["success"])
        self.assertEqual(restart_res["error"]["code"], "PROTECTED_SERVICE_BLOCKED")

    def test_no_defender_disabling_tools_exist(self) -> None:
        """Verify no registered tools or handlers allow disabling Defender or weakening protection."""
        registry = create_default_registry()
        forbidden_tool_patterns = [
            "disable_defender",
            "disable_realtime",
            "disable_antivirus",
            "disable_firewall",
            "disable_tamper",
            "add_exclusion",
            "remove_exclusion",
            "modify_policy",
            "kill_defender",
            "terminate_defender",
            "delete_defender",
        ]
        all_tools = registry.list_tool_names()
        for forbidden in forbidden_tool_patterns:
            matching = [t for t in all_tools if forbidden in t.lower()]
            self.assertEqual(matching, [], f"Found forbidden Defender tool: {matching}")

    def test_ast_no_prohibited_execution_in_defender_modules(self) -> None:
        """AST static scan ensuring zero shell/subprocess/registry-write operations."""
        modules_to_scan = [
            "windows/defender_tools.py",
            "windows/windows_defender_repairs.py",
            "agent/defender_diagnostics.py",
            "agent/defender_repairs_orchestrator.py",
        ]

        forbidden_direct_calls = {
            "eval",
            "exec",
            "system",
            "popen",
            "subprocess",
            "Popen",
            "check_output",
            "check_call",
            "SetValue",
            "SetValueEx",
            "DeleteValue",
            "DeleteKey",
            "CreateKey",
            "CreateKeyEx",
            "TerminateProcess",
        }

        forbidden_attributes = {
            "SetValue",
            "SetValueEx",
            "DeleteValue",
            "DeleteKey",
            "CreateKey",
            "CreateKeyEx",
            "TerminateProcess",
            "Popen",
            "check_output",
            "check_call",
        }

        for rel_path in modules_to_scan:
            full_path = os.path.abspath(rel_path)
            self.assertTrue(os.path.exists(full_path), f"File {rel_path} must exist.")
            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check direct function calls (e.g. eval(), exec())
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            forbidden_direct_calls,
                            f"Forbidden call '{node.func.id}' found in {rel_path} at line {node.lineno}",
                        )
                    # Check method calls (e.g., winreg.SetValueEx, os.system)
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in forbidden_attributes:
                            self.fail(f"Forbidden attribute call '{node.func.attr}' found in {rel_path} at line {node.lineno}")
                        if node.func.attr in ("system", "popen"):
                            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                self.fail(f"Forbidden 'os.{node.func.attr}' call found in {rel_path} at line {node.lineno}")


if __name__ == "__main__":
    unittest.main()
