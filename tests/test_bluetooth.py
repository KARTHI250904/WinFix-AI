"""Unit Tests for Windows Bluetooth Diagnostics & Controlled Repairs (Phase 11).

Covers:
1. Bluetooth adapter enumeration and hardware detection
2. Operational radio status analysis (ON, OFF, UNAVAILABLE, UNKNOWN)
3. Paired and active Bluetooth peripheral device enumeration
4. Bluetooth Support Service ('bthserv') inspection and dependency analysis
5. High-level unified diagnostic aggregator
6. ToolRegistry registration & safety risk classification (SAFE vs MEDIUM)
7. Cryptographic SHA-256 confirmation token binding & tamper detection
8. Controlled Bluetooth service restart execution with deterministic verification
9. Bluetooth diagnostics orchestrator scenarios (service stopped, disabled, hardware missing, radio off, healthy)
10. AST static security audit ensuring zero shell/subprocess/command strings
"""

import ast
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.bluetooth_diagnostics import (
    BLUETOOTH_CATEGORIES,
    BluetoothDiagnosis,
    BluetoothDiagnosticsOrchestrator,
)
from agent.bluetooth_repairs_orchestrator import (
    BluetoothRepairExecutionResult,
    BluetoothRepairProposal,
    BluetoothRepairsOrchestrator,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from database.db import DatabaseManager
from database.repositories import SessionRepository
from windows.bluetooth_repairs import (
    BLUETOOTH_SERVICE_NAME,
    restart_bluetooth_service,
)
from windows.bluetooth_tools import (
    get_bluetooth_adapters,
    get_bluetooth_devices,
    get_bluetooth_diagnostics,
    get_bluetooth_radio_status,
    get_bluetooth_service_status,
)


class TestBluetoothDiagnosticTools(unittest.TestCase):
    """Test suite for read-only Windows Bluetooth diagnostic tools."""

    @patch("windows.bluetooth_tools._query_wmi_bluetooth_entities")
    def test_get_bluetooth_adapters_present(self, mock_wmi: MagicMock) -> None:
        mock_wmi.return_value = [
            {
                "name": "Realtek Bluetooth Adapter",
                "description": "Realtek Bluetooth Adapter",
                "manufacturer": "Realtek",
                "device_id": "USB\\VID_13D3&PID_3571\\00E04C000001",
                "status": "OK",
                "pnp_class": "Bluetooth",
                "problem_code": 0,
                "is_enabled": True,
            }
        ]

        res = get_bluetooth_adapters()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_bluetooth_adapters")
        self.assertTrue(res["data"]["has_adapter"])
        self.assertEqual(res["data"]["adapter_count"], 1)
        self.assertEqual(res["data"]["primary_adapter"]["name"], "Realtek Bluetooth Adapter")
        self.assertEqual(res["data"]["primary_adapter"]["pnp_status"], "OK")

    @patch("windows.bluetooth_tools._query_wmi_bluetooth_entities")
    def test_get_bluetooth_adapters_missing(self, mock_wmi: MagicMock) -> None:
        mock_wmi.return_value = []

        res = get_bluetooth_adapters()
        self.assertTrue(res["success"])
        self.assertFalse(res["data"]["has_adapter"])
        self.assertEqual(res["data"]["adapter_count"], 0)
        self.assertIsNone(res["data"]["primary_adapter"])

    @patch("windows.bluetooth_tools.get_service_status")
    @patch("windows.bluetooth_tools.get_bluetooth_adapters")
    def test_get_bluetooth_radio_status_on(self, mock_adapters: MagicMock, mock_svc: MagicMock) -> None:
        mock_adapters.return_value = {
            "success": True,
            "data": {
                "has_adapter": True,
                "adapters": [{"name": "Intel Wireless Bluetooth", "problem_code": 0, "enabled": True}],
            },
        }
        mock_svc.return_value = {
            "success": True,
            "data": {"status": "RUNNING", "is_running": True},
        }

        res = get_bluetooth_radio_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["radio_status"], "ON")
        self.assertTrue(res["data"]["is_radio_on"])
        self.assertTrue(res["data"]["has_hardware"])

    @patch("windows.bluetooth_tools.get_service_status")
    @patch("windows.bluetooth_tools.get_bluetooth_adapters")
    def test_get_bluetooth_radio_status_off_service_stopped(self, mock_adapters: MagicMock, mock_svc: MagicMock) -> None:
        mock_adapters.return_value = {
            "success": True,
            "data": {
                "has_adapter": True,
                "adapters": [{"name": "Intel Wireless Bluetooth", "problem_code": 0, "enabled": True}],
            },
        }
        mock_svc.return_value = {
            "success": True,
            "data": {"status": "STOPPED", "is_running": False},
        }

        res = get_bluetooth_radio_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["radio_status"], "OFF")
        self.assertFalse(res["data"]["is_radio_on"])

    @patch("windows.bluetooth_tools.get_service_status")
    @patch("windows.bluetooth_tools.get_bluetooth_adapters")
    def test_get_bluetooth_radio_status_unavailable_no_hardware(self, mock_adapters: MagicMock, mock_svc: MagicMock) -> None:
        mock_adapters.return_value = {
            "success": True,
            "data": {"has_adapter": False, "adapters": []},
        }
        mock_svc.return_value = {
            "success": True,
            "data": {"status": "STOPPED", "is_running": False},
        }

        res = get_bluetooth_radio_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["radio_status"], "UNAVAILABLE")
        self.assertFalse(res["data"]["has_hardware"])

    @patch("windows.bluetooth_tools._query_wmi_bluetooth_entities")
    def test_get_bluetooth_devices_paired(self, mock_wmi: MagicMock) -> None:
        mock_wmi.return_value = [
            {
                "name": "Sony WH-1000XM4",
                "description": "Bluetooth Audio Device",
                "manufacturer": "Sony",
                "device_id": "BTHENUM\\DEV_94DB56000000\\7&310c1285&0&BLUETOOTHDEVICE_94DB56000000",
                "status": "OK",
                "pnp_class": "Bluetooth",
                "problem_code": 0,
                "is_enabled": True,
            },
            {
                "name": "Logitech MX Master 3",
                "description": "Bluetooth HID Device",
                "manufacturer": "Logitech",
                "device_id": "BTHLE\\DEV_E41218000000\\8&210c1285&0&BLUETOOTHDEVICE_E41218000000",
                "status": "OK",
                "pnp_class": "Bluetooth",
                "problem_code": 0,
                "is_enabled": True,
            },
        ]

        res = get_bluetooth_devices()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_bluetooth_devices")
        self.assertEqual(res["data"]["device_count"], 2)
        self.assertEqual(res["data"]["connected_count"], 2)
        self.assertEqual(res["data"]["devices"][0]["name"], "Sony WH-1000XM4")

    @patch("windows.bluetooth_tools.get_service_status")
    def test_get_bluetooth_service_status(self, mock_status: MagicMock) -> None:
        mock_status.return_value = {
            "success": True,
            "data": {
                "name": "bthserv",
                "display_name": "Bluetooth Support Service",
                "status": "RUNNING",
                "start_type": "DEMAND",
                "is_running": True,
            },
        }

        res = get_bluetooth_service_status()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["service_name"], "bthserv")
        self.assertTrue(res["data"]["service_running"])
        self.assertEqual(res["data"]["status"], "RUNNING")
        self.assertFalse(res["data"]["is_disabled"])

    @patch("windows.bluetooth_tools.get_bluetooth_service_status")
    @patch("windows.bluetooth_tools.get_bluetooth_devices")
    @patch("windows.bluetooth_tools.get_bluetooth_radio_status")
    @patch("windows.bluetooth_tools.get_bluetooth_adapters")
    def test_get_bluetooth_diagnostics_aggregator(
        self,
        mock_adapters: MagicMock,
        mock_radio: MagicMock,
        mock_devices: MagicMock,
        mock_svc: MagicMock,
    ) -> None:
        mock_adapters.return_value = {"success": True, "data": {"has_adapter": True, "adapters": [{"name": "Intel Bluetooth"}]}}
        mock_radio.return_value = {"success": True, "data": {"radio_status": "ON", "is_radio_on": True}}
        mock_devices.return_value = {"success": True, "data": {"device_count": 1, "connected_count": 1, "devices": [{"name": "Mouse"}]}}
        mock_svc.return_value = {"success": True, "data": {"service_running": True, "status": "RUNNING", "start_type": "DEMAND"}}

        res = get_bluetooth_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["health"], "HEALTHY")
        self.assertTrue(res["data"]["adapter_detected"])
        self.assertTrue(res["data"]["service_running"])
        self.assertEqual(res["data"]["paired_devices_count"], 1)


class TestBluetoothToolRegistryAndMetadata(unittest.TestCase):
    """Test suite verifying ToolRegistry registration and risk classifications for Phase 11 tools."""

    def setUp(self) -> None:
        self.registry = create_default_registry()

    def test_registered_tool_count(self) -> None:
        # Total tools: 29 SAFE + 8 MEDIUM = 37 tools
        self.assertEqual(self.registry.count(), 37)

    def test_phase11_diagnostic_tools_metadata(self) -> None:
        diag_tools = [
            "get_bluetooth_diagnostics",
            "get_bluetooth_adapters",
            "get_bluetooth_radio_status",
            "get_bluetooth_devices",
            "get_bluetooth_service_status",
        ]
        for t_name in diag_tools:
            tool = self.registry.get(t_name)
            self.assertIsNotNone(tool, f"Diagnostic tool '{t_name}' must be registered.")
            self.assertEqual(tool.risk, RiskLevel.SAFE)
            self.assertTrue(tool.read_only)
            self.assertTrue(tool.automatic_allowed)
            self.assertFalse(tool.requires_admin)

    def test_phase11_repair_tool_metadata(self) -> None:
        tool = self.registry.get("restart_bluetooth_service")
        self.assertIsNotNone(tool, "Repair tool 'restart_bluetooth_service' must be registered.")
        self.assertEqual(tool.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool.read_only)
        self.assertFalse(tool.automatic_allowed)
        self.assertTrue(tool.requires_admin)
        self.assertEqual(tool.verification_tool, "get_service_status")


class TestBluetoothControlledRepairs(unittest.TestCase):
    """Test suite for controlled Bluetooth repair operations with deterministic verification."""

    @patch("windows.bluetooth_repairs.restart_service")
    @patch("windows.bluetooth_repairs.get_service_status")
    def test_restart_bluetooth_service_success(self, mock_status: MagicMock, mock_restart: MagicMock) -> None:
        mock_status.return_value = {
            "success": True,
            "data": {"name": "bthserv", "status": "STOPPED", "is_running": False},
        }
        mock_restart.return_value = {
            "success": True,
            "data": {
                "service_name": "bthserv",
                "before_state": "STOPPED",
                "after_state": "RUNNING",
                "verification": "verified",
            },
            "error": None,
        }

        res = restart_bluetooth_service()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["service_name"], "bthserv")
        self.assertEqual(res["data"]["verification"], "verified")
        self.assertEqual(res["data"]["after_state"], "RUNNING")

    @patch("windows.bluetooth_repairs.restart_service")
    @patch("windows.bluetooth_repairs.get_service_status")
    def test_restart_bluetooth_service_stop_failure(self, mock_status: MagicMock, mock_restart: MagicMock) -> None:
        mock_status.return_value = {
            "success": True,
            "data": {"name": "bthserv", "status": "RUNNING", "is_running": True},
        }
        mock_restart.return_value = {
            "success": False,
            "data": {
                "service_name": "bthserv",
                "before_state": "RUNNING",
                "after_state": "RUNNING",
                "verification": "failed",
            },
            "error": {"code": "STOP_FAILED", "message": "Failed to stop bthserv."},
        }

        res = restart_bluetooth_service()
        self.assertFalse(res["success"])
        self.assertEqual(res["data"]["verification"], "failed")
        self.assertEqual(res["error"]["code"], "STOP_FAILED")


class TestBluetoothConfirmationAndOrchestrator(unittest.TestCase):
    """Test suite for Bluetooth confirmation token binding, tamper detection, and orchestrator execution."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bth.db")
        self.schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "schema.sql")
        self.db = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db.init_db()

        self.safety_engine = SafetyEngine()
        self.orchestrator = BluetoothRepairsOrchestrator(
            safety_engine=self.safety_engine,
            db_mgr=self.db,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_confirmation_token_binding(self) -> None:
        proposal = BluetoothRepairProposal()
        token = proposal.generate_confirmation_token(session_id="sess_bth_1")
        self.assertTrue(self.orchestrator.validate_confirmation_token(token, "restart_bluetooth_service", {}, "sess_bth_1"))

    def test_confirmation_token_tamper_detection(self) -> None:
        proposal = BluetoothRepairProposal()
        token = proposal.generate_confirmation_token(session_id="sess_bth_1")

        # Wrong tool name
        self.assertFalse(self.orchestrator.validate_confirmation_token(token, "stop_service", {}, "sess_bth_1"))
        # Tampered arguments
        self.assertFalse(self.orchestrator.validate_confirmation_token(token, "restart_bluetooth_service", {"extra": 1}, "sess_bth_1"))
        # Wrong session id
        self.assertFalse(self.orchestrator.validate_confirmation_token(token, "restart_bluetooth_service", {}, "sess_bth_999"))

    @patch("agent.safety.SafetyEngine.execute")
    def test_execute_confirmed_repair_success(self, mock_exec: MagicMock) -> None:
        SessionRepository(self.db).create(session_id="sess_bth_1")

        mock_exec.side_effect = [
            # Before get_service_status
            {"success": True, "data": {"name": "bthserv", "status": "STOPPED"}},
            # restart_bluetooth_service repair
            {"success": True, "data": {"service_name": "bthserv", "operation": "restart", "after_state": "RUNNING"}},
            # After get_service_status
            {"success": True, "data": {"name": "bthserv", "status": "RUNNING"}},
        ]

        token = BluetoothRepairProposal().generate_confirmation_token("sess_bth_1")

        res = self.orchestrator.execute_confirmed_repair(
            tool_name="restart_bluetooth_service",
            arguments={},
            confirmation_token=token,
            session_id="sess_bth_1",
        )

        self.assertTrue(res.confirmed)
        self.assertTrue(res.repair_success)
        self.assertEqual(res.verification_status, "verified")
        self.assertEqual(res.before_state.get("status"), "STOPPED")
        self.assertEqual(res.after_state.get("status"), "RUNNING")


class TestBluetoothDiagnosticsScenarios(unittest.TestCase):
    """Test suite for BluetoothDiagnosticsOrchestrator scenario deductions."""

    def setUp(self) -> None:
        self.safety_engine = SafetyEngine()
        self.diag_orchestrator = BluetoothDiagnosticsOrchestrator(safety_engine=self.safety_engine)

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_service_stopped(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "health": "ERROR",
                "adapter_detected": True,
                "adapters": [{"name": "Intel Bluetooth", "enabled": True, "problem_code": 0}],
                "radio": {"radio_status": "OFF", "is_radio_on": False},
                "service": {"service_running": False, "status": "STOPPED", "start_type": "DEMAND"},
                "devices": [],
            },
        }

        diagnosis = self.diag_orchestrator.run_diagnostics()
        self.assertEqual(diagnosis.problem_category, "service_stopped")
        self.assertTrue(diagnosis.repair_available)
        self.assertEqual(diagnosis.proposed_tool, "restart_bluetooth_service")

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_adapter_missing(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "health": "UNAVAILABLE",
                "adapter_detected": False,
                "adapters": [],
                "radio": {"radio_status": "UNAVAILABLE", "is_radio_on": False},
                "service": {"service_running": False, "status": "STOPPED", "start_type": "DEMAND"},
                "devices": [],
            },
        }

        diagnosis = self.diag_orchestrator.run_diagnostics()
        self.assertEqual(diagnosis.problem_category, "adapter_missing")
        self.assertFalse(diagnosis.repair_available)

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_service_disabled(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "health": "ERROR",
                "adapter_detected": True,
                "adapters": [{"name": "Intel Bluetooth"}],
                "radio": {"radio_status": "OFF"},
                "service": {"service_running": False, "status": "STOPPED", "start_type": "DISABLED"},
                "devices": [],
            },
        }

        diagnosis = self.diag_orchestrator.run_diagnostics()
        self.assertEqual(diagnosis.problem_category, "service_disabled")
        self.assertFalse(diagnosis.repair_available)

    @patch("agent.safety.SafetyEngine.execute")
    def test_scenario_healthy(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = {
            "success": True,
            "data": {
                "health": "HEALTHY",
                "adapter_detected": True,
                "adapters": [{"name": "Realtek Bluetooth"}],
                "radio": {"radio_status": "ON"},
                "service": {"service_running": True, "status": "RUNNING", "start_type": "DEMAND"},
                "devices": [{"name": "Bluetooth Headphones"}],
            },
        }

        diagnosis = self.diag_orchestrator.run_diagnostics()
        self.assertEqual(diagnosis.problem_category, "general_bluetooth")
        self.assertFalse(diagnosis.repair_available)


class TestASTStaticSecurityAuditBluetooth(unittest.TestCase):
    """AST static security scanner ensuring zero forbidden execution patterns in Phase 11 Bluetooth modules."""

    def test_zero_forbidden_abstractions_in_phase11_code(self) -> None:
        forbidden_strings = [
            "sc.exe",
            "cmd.exe",
            "powershell.exe",
            "pwsh.exe",
            "net.exe",
            "devcon.exe",
            "pnputil.exe",
            "taskkill",
            "TerminateProcess",
        ]

        files_to_scan = [
            "windows/bluetooth_tools.py",
            "windows/bluetooth_repairs.py",
            "agent/bluetooth_diagnostics.py",
            "agent/bluetooth_repairs_orchestrator.py",
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

            # Check for forbidden command strings
            for s in forbidden_strings:
                self.assertNotIn(f'"{s}"', source, f"Forbidden string '\"{s}\"' found in {rel_path}")
                self.assertNotIn(f"'{s}'", source, f"Forbidden string \"'{s}'\" found in {rel_path}")


if __name__ == "__main__":
    unittest.main()
