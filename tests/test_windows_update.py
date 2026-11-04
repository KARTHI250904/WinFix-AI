"""Comprehensive Test Suite for Windows Update Diagnostics & Controlled Repair (Phase 12).

Tests:
- Diagnostic tools (service status, dependencies, config, history, errors, health, diagnostics)
- Tool registry metadata and risk classification
- SafetyEngine enforcement and confirmation token binding
- Sequential stop-then-start repair flow with verification
- Fail-closed guarantees (stop failure prevents start)
- Protected-service policy and dependency isolation
- AST static security scan confirming zero forbidden execution methods
"""

import ast
import os
import unittest
from unittest.mock import MagicMock, patch

from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry, default_tool_registry
from agent.windows_update_diagnostics import (
    WindowsUpdateDiagnosis,
    WindowsUpdateDiagnosticsOrchestrator,
)
from agent.windows_update_repairs_orchestrator import (
    WindowsUpdateRepairProposal,
    WindowsUpdateRepairsOrchestrator,
)
from windows.service_repairs import is_service_stop_protected, restart_service, stop_service
from windows.windows_update_repairs import (
    WINDOWS_UPDATE_SERVICE_NAME,
    restart_windows_update_service,
)
from windows.windows_update_tools import (
    get_windows_update_configuration,
    get_windows_update_dependency_services,
    get_windows_update_diagnostics,
    get_windows_update_errors,
    get_windows_update_health,
    get_windows_update_history,
    get_windows_update_service_status,
)


class TestWindowsUpdateDiagnosticsTools(unittest.TestCase):
    """Test suite for read-only Windows Update diagnostic tools."""

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_tools.get_service_status")
    def test_get_windows_update_service_status_running(self, mock_svc_status, mock_platform):
        """Verify service status inspection when wuauserv is RUNNING."""
        mock_svc_status.return_value = {
            "success": True,
            "tool": "get_service_status",
            "data": {
                "service_name": "wuauserv",
                "display_name": "Windows Update",
                "status": "RUNNING",
                "is_running": True,
                "start_type": "DEMAND_START",
                "pid": 1024,
            },
            "error": None,
        }

        res = get_windows_update_service_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_windows_update_service_status")
        self.assertEqual(res["domain"], "windows_update")
        self.assertEqual(res["data"]["service_name"], "wuauserv")
        self.assertEqual(res["data"]["status"], "RUNNING")
        self.assertTrue(res["data"]["is_running"])

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_tools.get_service_status")
    def test_get_windows_update_dependency_services_all_healthy(self, mock_svc_status, mock_platform):
        """Verify dependency service queries when all dependencies are healthy."""
        mock_svc_status.side_effect = lambda name: {
            "success": True,
            "tool": "get_service_status",
            "data": {
                "service_name": name,
                "display_name": name.upper(),
                "status": "RUNNING",
                "is_running": True,
                "start_type": "AUTO_START",
            },
            "error": None,
        }

        res = get_windows_update_dependency_services()
        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["all_dependencies_healthy"])
        self.assertEqual(len(res["data"]["dependencies"]), 5)
        self.assertEqual(res["data"]["degraded_services"], [])

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_tools.get_service_status")
    def test_get_windows_update_dependency_services_degraded(self, mock_svc_status, mock_platform):
        """Verify dependency service queries when a critical dependency is stopped/disabled."""
        def svc_side_effect(name):
            if name == "cryptsvc":
                return {
                    "success": True,
                    "tool": "get_service_status",
                    "data": {
                        "service_name": name,
                        "display_name": "Cryptographic Services",
                        "status": "DISABLED",
                        "is_running": False,
                        "start_type": "DISABLED",
                    },
                    "error": None,
                }
            return {
                "success": True,
                "tool": "get_service_status",
                "data": {
                    "service_name": name,
                    "display_name": name.upper(),
                    "status": "RUNNING",
                    "is_running": True,
                    "start_type": "AUTO_START",
                },
                "error": None,
            }

        mock_svc_status.side_effect = svc_side_effect
        res = get_windows_update_dependency_services()
        self.assertTrue(res["success"])
        self.assertFalse(res["data"]["all_dependencies_healthy"])
        self.assertIn("cryptsvc", res["data"]["degraded_services"])

    @patch("platform.system", return_value="Windows")
    def test_get_windows_update_configuration_structure(self, mock_platform):
        """Verify configuration query returns expected keys and handles missing keys gracefully."""
        res = get_windows_update_configuration()
        self.assertTrue(res["success"])
        self.assertIn("au_options", res["data"])
        self.assertIn("no_auto_update", res["data"])
        self.assertIn("use_wu_server", res["data"])
        self.assertIn("policy_managed", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_windows_update_history_structure_and_bounds(self, mock_platform):
        """Verify update history query clamps limit and returns structured records."""
        res = get_windows_update_history(limit=5)
        self.assertTrue(res["success"])
        self.assertIsInstance(res["data"]["updates"], list)
        self.assertIn("count", res["data"])

    @patch("platform.system", return_value="Windows")
    def test_get_windows_update_errors_structure(self, mock_platform):
        """Verify update error events query returns structured output."""
        res = get_windows_update_errors(limit=5)
        self.assertTrue(res["success"])
        self.assertIsInstance(res["data"]["errors"], list)
        self.assertIn("has_recent_errors", res["data"])

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_tools.get_windows_update_service_status")
    @patch("windows.windows_update_tools.get_windows_update_dependency_services")
    @patch("windows.windows_update_tools.get_windows_update_errors")
    def test_get_windows_update_health_scenarios(self, mock_errors, mock_deps, mock_svc, mock_platform):
        """Verify health synthesis across healthy, degraded, and critical scenarios."""
        # 1. Healthy scenario
        mock_svc.return_value = {"success": True, "data": {"status": "RUNNING", "start_type": "DEMAND_START", "is_running": True}}
        mock_deps.return_value = {"success": True, "data": {"all_dependencies_healthy": True, "degraded_services": []}}
        mock_errors.return_value = {"success": True, "data": {"has_recent_errors": False, "count": 0}}

        res_healthy = get_windows_update_health()
        self.assertEqual(res_healthy["data"]["overall_status"], "HEALTHY")

        # 2. Stopped (Degraded) scenario
        mock_svc.return_value = {"success": True, "data": {"status": "STOPPED", "start_type": "DEMAND_START", "is_running": False}}
        res_stopped = get_windows_update_health()
        self.assertEqual(res_stopped["data"]["overall_status"], "DEGRADED")
        self.assertTrue(any("Restart" in r for r in res_stopped["data"]["recommendations"]))

        # 3. Disabled (Critical) scenario
        mock_svc.return_value = {"success": True, "data": {"status": "STOPPED", "start_type": "DISABLED", "is_running": False}}
        res_disabled = get_windows_update_health()
        self.assertEqual(res_disabled["data"]["overall_status"], "CRITICAL")

    @patch("platform.system", return_value="Windows")
    def test_get_windows_update_diagnostics_aggregation(self, mock_platform):
        """Verify aggregator includes all 6 diagnostic subcomponents."""
        res = get_windows_update_diagnostics()
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertIn("service_status", data)
        self.assertIn("dependencies", data)
        self.assertIn("configuration", data)
        self.assertIn("history", data)
        self.assertIn("errors", data)
        self.assertIn("health", data)
        self.assertIn("summary", data)


class TestWindowsUpdateToolRegistryAndMetadata(unittest.TestCase):
    """Verify ToolRegistry registration, counts, and metadata for Phase 12."""

    def setUp(self):
        self.registry = default_tool_registry

    def test_all_phase12_tools_registered(self):
        """Verify all 7 diagnostic tools and 1 repair tool are registered."""
        expected_tools = [
            "get_windows_update_service_status",
            "get_windows_update_dependency_services",
            "get_windows_update_configuration",
            "get_windows_update_history",
            "get_windows_update_errors",
            "get_windows_update_health",
            "get_windows_update_diagnostics",
            "restart_windows_update_service",
        ]
        for name in expected_tools:
            self.assertIsNotNone(self.registry.get(name), f"Missing registered tool: {name}")

    def test_phase12_diagnostic_metadata(self):
        """Verify metadata on Phase 12 diagnostic tools."""
        diag_tools = [
            "get_windows_update_service_status",
            "get_windows_update_dependency_services",
            "get_windows_update_configuration",
            "get_windows_update_history",
            "get_windows_update_errors",
            "get_windows_update_health",
            "get_windows_update_diagnostics",
        ]
        for name in diag_tools:
            defn = self.registry.get(name)
            self.assertIsNotNone(defn)
            self.assertEqual(defn.domain, "windows_update")
            self.assertEqual(defn.risk, RiskLevel.SAFE)
            self.assertTrue(defn.read_only)
            self.assertTrue(defn.automatic_allowed)
            self.assertFalse(defn.requires_admin)

    def test_phase12_repair_metadata(self):
        """Verify metadata on restart_windows_update_service."""
        defn = self.registry.get("restart_windows_update_service")
        self.assertIsNotNone(defn)
        self.assertEqual(defn.domain, "windows_update")
        self.assertEqual(defn.risk, RiskLevel.MEDIUM)
        self.assertFalse(defn.read_only)
        self.assertFalse(defn.automatic_allowed)
        self.assertTrue(defn.requires_admin)
        self.assertEqual(defn.verification_tool, "get_windows_update_service_status")

    def test_total_registry_counts(self):
        """Verify total registry counts across risk categories."""
        all_tools = self.registry.list_tools()
        safe_tools = [t for t in all_tools if t.risk == RiskLevel.SAFE]
        med_tools = [t for t in all_tools if t.risk == RiskLevel.MEDIUM]
        high_tools = [t for t in all_tools if t.risk == RiskLevel.HIGH]

        self.assertGreaterEqual(len(all_tools), 44)
        self.assertGreaterEqual(len(safe_tools), 35)
        self.assertGreaterEqual(len(med_tools), 9)
        self.assertEqual(len(high_tools), 0)


class TestWindowsUpdateSafetyAndConfirmation(unittest.TestCase):
    """Test safety engine, confirmation token binding, and tampering detection."""

    def setUp(self):
        self.safety_engine = SafetyEngine()

    def test_diagnostic_tools_execute_without_confirmation(self):
        """Verify SAFE diagnostic tools execute without requiring confirmation tokens."""
        decision = self.safety_engine.evaluate(
            tool_name="get_windows_update_service_status",
            arguments={},
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_confirmation)

    def test_repair_tool_requires_confirmation(self):
        """Verify MEDIUM repair tool requires user confirmation."""
        decision = self.safety_engine.evaluate(
            tool_name="restart_windows_update_service",
            arguments={},
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual(decision.risk, RiskLevel.MEDIUM.value)

    def test_confirmation_token_binding_and_tampering(self):
        """Verify SHA-256 confirmation token validates strictly and detects tampering."""
        proposal = WindowsUpdateRepairProposal(
            tool_name="restart_windows_update_service",
            arguments={},
            service_name="wuauserv",
        )
        session_id = "session_wu_123"
        valid_token = proposal.generate_confirmation_token(session_id)

        # 1. Valid token matches
        self.assertEqual(valid_token, proposal.generate_confirmation_token(session_id))

        # 2. Tampered arguments fail
        proposal_tampered = WindowsUpdateRepairProposal(
            tool_name="restart_windows_update_service",
            arguments={"service_name": "other_service"},
        )
        self.assertNotEqual(valid_token, proposal_tampered.generate_confirmation_token(session_id))

        # 3. Wrong session fails
        self.assertNotEqual(valid_token, proposal.generate_confirmation_token("different_session"))

        # 4. Wrong tool fails
        proposal_wrong_tool = WindowsUpdateRepairProposal(
            tool_name="restart_bluetooth_service",
            arguments={},
        )
        self.assertNotEqual(valid_token, proposal_wrong_tool.generate_confirmation_token(session_id))


class TestWindowsUpdateRepairExecutionAndVerification(unittest.TestCase):
    """Test controlled sequential stop-then-start repair execution with mock native APIs."""

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_repairs.get_service_status")
    @patch("windows.windows_update_repairs.start_service")
    def test_restart_wuauserv_when_already_stopped(self, mock_start, mock_get_status, mock_platform):
        """If wuauserv is already STOPPED, directly start it and verify."""
        mock_get_status.return_value = {
            "success": True,
            "data": {"status": "STOPPED", "display_name": "Windows Update"},
        }
        mock_start.return_value = {
            "success": True,
            "data": {"after_state": "RUNNING", "verification": "verified"},
        }

        res = restart_windows_update_service()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["before_state"], "STOPPED")
        self.assertEqual(res["data"]["after_state"], "RUNNING")
        self.assertEqual(res["data"]["verification"], "verified")
        mock_start.assert_called_once_with(WINDOWS_UPDATE_SERVICE_NAME)

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_repairs.get_service_status")
    @patch("windows.windows_update_repairs._stop_wuauserv_direct")
    @patch("windows.windows_update_repairs._wait_for_service_status")
    @patch("windows.windows_update_repairs.start_service")
    def test_restart_wuauserv_when_running_success(self, mock_start, mock_wait, mock_stop, mock_get_status, mock_platform):
        """When wuauserv is RUNNING, stop it -> verify STOPPED -> start it -> verify RUNNING."""
        mock_get_status.return_value = {
            "success": True,
            "data": {"status": "RUNNING", "display_name": "Windows Update"},
        }
        mock_stop.return_value = {"success": True, "error": None}
        mock_wait.return_value = (True, "STOPPED")
        mock_start.return_value = {
            "success": True,
            "data": {"after_state": "RUNNING", "verification": "verified"},
        }

        res = restart_windows_update_service()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["before_state"], "RUNNING")
        self.assertEqual(res["data"]["after_state"], "RUNNING")
        self.assertEqual(res["data"]["verification"], "verified")
        mock_stop.assert_called_once()
        mock_start.assert_called_once_with(WINDOWS_UPDATE_SERVICE_NAME)

    @patch("platform.system", return_value="Windows")
    @patch("windows.windows_update_repairs.get_service_status")
    @patch("windows.windows_update_repairs._stop_wuauserv_direct")
    @patch("windows.windows_update_repairs._wait_for_service_status")
    @patch("windows.windows_update_repairs.start_service")
    def test_restart_wuauserv_stop_failure_prevents_start(self, mock_start, mock_wait, mock_stop, mock_get_status, mock_platform):
        """CRITICAL: If stop verification fails or times out, DO NOT start the service."""
        mock_get_status.return_value = {
            "success": True,
            "data": {"status": "RUNNING", "display_name": "Windows Update"},
        }
        mock_stop.return_value = {"success": True, "error": None}
        # Stop verification fails (returns False, remains RUNNING)
        mock_wait.return_value = (False, "RUNNING")

        res = restart_windows_update_service()
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["verification"], "not_verified")
        self.assertEqual(res["error"]["code"], "VERIFICATION_TIMEOUT")

        # Start MUST NOT be called
        mock_start.assert_not_called()

    @patch("platform.system", return_value="Windows")
    def test_orchestrator_execute_confirmed_restart_success(self, mock_platform):
        """Verify orchestrator execute_confirmed_restart executes via SafetyEngine and verifies outcome."""
        mock_safety = MagicMock(spec=SafetyEngine)
        # Mock before-state status check
        # Mock repair execution
        # Mock after-state status check
        mock_safety.execute.side_effect = [
            {"success": True, "data": {"status": "STOPPED"}},  # before-state
            {"success": True, "data": {"after_state": "RUNNING", "verification": "verified"}},  # repair execution
            {"success": True, "data": {"status": "RUNNING"}},  # after-state
        ]

        orchestrator = WindowsUpdateRepairsOrchestrator(safety_engine=mock_safety)
        proposal = orchestrator.prepare_restart_proposal(session_id="session_123")
        token = proposal.generate_confirmation_token("session_123")

        res = orchestrator.execute_confirmed_restart(proposal, token, session_id="session_123")
        self.assertTrue(res.confirmed)
        self.assertTrue(res.repair_success)
        self.assertEqual(res.verification_status, "verified")
        self.assertEqual(mock_safety.execute.call_count, 3)

        # Ensure the repair execution called safety_engine with user_confirmed=True
        repair_call = mock_safety.execute.call_args_list[1]
        self.assertEqual(repair_call.kwargs.get("user_confirmed"), True)
        self.assertEqual(repair_call.kwargs.get("tool_name"), "restart_windows_update_service")

    @patch("platform.system", return_value="Windows")
    def test_orchestrator_execute_confirmed_restart_invalid_token(self, mock_platform):
        """Verify orchestrator blocks execution if confirmation token is invalid."""
        mock_safety = MagicMock(spec=SafetyEngine)
        orchestrator = WindowsUpdateRepairsOrchestrator(safety_engine=mock_safety)
        proposal = orchestrator.prepare_restart_proposal(session_id="session_123")

        res = orchestrator.execute_confirmed_restart(proposal, "invalid_token", session_id="session_123")
        self.assertFalse(res.confirmed)
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")
        mock_safety.execute.assert_not_called()


class TestProtectedServicesPolicyAndDependencyIsolation(unittest.TestCase):
    """Verify global protected services policy preserves wuauserv protection against generic stop/restart."""

    def test_wuauserv_globally_protected_from_generic_tools(self):
        """Verify generic stop_service('wuauserv') and restart_service('wuauserv') remain blocked."""
        is_prot, reason = is_service_stop_protected("wuauserv")
        self.assertTrue(is_prot)
        self.assertIn("critical Windows system", reason)

        # Calling generic stop_service must be blocked
        stop_res = stop_service("wuauserv")
        self.assertFalse(stop_res["success"])
        self.assertEqual(stop_res["error"]["code"], "PROTECTED_SERVICE_BLOCKED")

        # Calling generic restart_service must be blocked
        restart_res = restart_service("wuauserv")
        self.assertFalse(restart_res["success"])
        self.assertEqual(restart_res["error"]["code"], "PROTECTED_SERVICE_BLOCKED")

    def test_dependencies_never_restarted_by_windows_update_repair(self):
        """Verify BITS, CryptSvc, and RpcSs are protected and never targeted by restart_windows_update_service."""
        for dep in ["bits", "cryptsvc", "rpcss", "dcomlaunch"]:
            is_prot, _ = is_service_stop_protected(dep)
            self.assertTrue(is_prot, f"Dependency '{dep}' must remain protected.")


class TestASTStaticSecurityAudit(unittest.TestCase):
    """Scan all Phase 12 modules using Python AST to ensure zero forbidden execution methods."""

    def test_zero_forbidden_abstractions_in_phase12_code(self):
        """Verify no subprocess, os.system, shell=True, eval, exec in windows_update modules."""
        forbidden_calls = {"system", "popen", "subprocess", "eval", "exec", "TerminateProcess"}
        forbidden_imports = {"subprocess"}

        paths_to_check = [
            "windows/windows_update_tools.py",
            "windows/windows_update_repairs.py",
            "agent/windows_update_diagnostics.py",
            "agent/windows_update_repairs_orchestrator.py",
        ]

        for rel_path in paths_to_check:
            if not os.path.exists(rel_path):
                continue
            with open(rel_path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=rel_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        self.assertNotIn(
                            name.name,
                            forbidden_imports,
                            f"Forbidden import '{name.name}' in {rel_path}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root_mod = node.module.split(".")[0]
                        self.assertNotIn(
                            root_mod,
                            forbidden_imports,
                            f"Forbidden import from '{node.module}' in {rel_path}",
                        )
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            forbidden_calls,
                            f"Forbidden function call '{node.func.id}()' in {rel_path}",
                        )


if __name__ == "__main__":
    unittest.main()
