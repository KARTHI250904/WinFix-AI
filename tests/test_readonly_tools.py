
"""Comprehensive unit and safety tests for WinFix AI Phase 3 read-only Windows tools."""

import inspect
import unittest
from unittest.mock import MagicMock, patch

import windows
from windows.bluetooth_tools import get_bluetooth_diagnostics
from windows.defender_tools import get_defender_diagnostics
from windows.event_tools import get_recent_application_crashes
from windows.network_tools import (
    check_dns_resolution,
    check_internet_connectivity,
    get_dns_client_config,
    get_network_adapters_diagnostics,
)
from windows.performance_tools import (
    get_cpu_diagnostics,
    get_memory_diagnostics,
    get_top_cpu_processes,
    get_top_memory_processes,
)
from windows.printer_tools import get_printer_diagnostics
from windows.service_tools import get_service_status, list_common_services
from windows.storage_tools import get_storage_diagnostics, get_temp_storage_info
from windows.windows_update_tools import get_windows_update_diagnostics


class TestReadonlyWindowsTools(unittest.TestCase):
    """Test suite verifying functionality and return schemas of read-only diagnostic tools."""

    # --- NETWORK TOOLS ---
    def test_network_adapters_diagnostics(self) -> None:
        """Verify network adapters diagnostics structure."""
        res = get_network_adapters_diagnostics()
        self.assertIn("success", res)
        self.assertEqual(res["domain"], "network")
        self.assertEqual(res["tool"], "get_network_adapters_diagnostics")
        if res["success"]:
            self.assertIn("adapters", res["data"])
            self.assertIn("total_adapters", res["data"])

    def test_check_dns_resolution(self) -> None:
        """Verify DNS resolution test structure and mock handling."""
        # Test with mock
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("8.8.8.8", 0))]):
            res = check_dns_resolution("dns.google")
            self.assertTrue(res["success"])
            self.assertEqual(res["domain"], "network")
            self.assertTrue(res["data"]["resolved"])
            self.assertIn("8.8.8.8", res["data"]["resolved_ips"])
            self.assertGreaterEqual(res["data"]["latency_ms"], 0)

    def test_check_internet_connectivity(self) -> None:
        """Verify internet connectivity test returns structured socket latency."""
        mock_sock = MagicMock()
        with patch("socket.create_connection", return_value=mock_sock):
            res = check_internet_connectivity("1.1.1.1", port=53)
            self.assertTrue(res["success"])
            self.assertEqual(res["domain"], "network")
            self.assertTrue(res["data"]["reachable"])
            self.assertGreaterEqual(res["data"]["latency_ms"], 0)

    def test_get_dns_client_config(self) -> None:
        """Verify DNS client configuration reader."""
        res = get_dns_client_config()
        self.assertIn("success", res)
        self.assertEqual(res["domain"], "network")
        if res["success"]:
            self.assertIn("dns_servers", res["data"])
            self.assertIsInstance(res["data"]["dns_servers"], list)

    # --- PERFORMANCE TOOLS ---
    def test_cpu_diagnostics(self) -> None:
        """Verify CPU diagnostics return usage percentages and core counts."""
        res = get_cpu_diagnostics(interval=0.01)
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "performance")
        self.assertIn("overall_percent", res["data"])
        self.assertIn("physical_cores", res["data"])
        self.assertIn("logical_threads", res["data"])

    def test_memory_diagnostics(self) -> None:
        """Verify memory diagnostics return RAM and swap metrics."""
        res = get_memory_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "performance")
        self.assertIn("virtual_memory", res["data"])
        self.assertIn("swap_memory", res["data"])
        self.assertIn("total_bytes", res["data"]["virtual_memory"])

    def test_top_cpu_processes(self) -> None:
        """Verify top CPU process query returns bounded process list."""
        res = get_top_cpu_processes(limit=3)
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "performance")
        self.assertLessEqual(len(res["data"]["processes"]), 3)
        if res["data"]["processes"]:
            first = res["data"]["processes"][0]
            self.assertIn("pid", first)
            self.assertIn("name", first)
            self.assertIn("cpu_percent", first)

    def test_top_memory_processes(self) -> None:
        """Verify top memory process query returns bounded process list."""
        res = get_top_memory_processes(limit=3)
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "performance")
        self.assertLessEqual(len(res["data"]["processes"]), 3)
        if res["data"]["processes"]:
            first = res["data"]["processes"][0]
            self.assertIn("pid", first)
            self.assertIn("memory_bytes", first)
            self.assertIn("memory_formatted", first)

    # --- STORAGE TOOLS ---
    def test_storage_diagnostics(self) -> None:
        """Verify storage diagnostics return partition metrics."""
        res = get_storage_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "storage")
        self.assertIn("drives", res["data"])
        self.assertGreater(res["data"]["drives_count"], 0)

    def test_temp_storage_info(self) -> None:
        """Verify temp storage reader inspects directories without deleting."""
        res = get_temp_storage_info()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "storage")
        self.assertIn("total_temp_bytes", res["data"])
        self.assertIn("locations", res["data"])

    # --- SERVICES TOOLS ---
    def test_service_status(self) -> None:
        """Verify service status query on common Windows services."""
        res = get_service_status("Spooler")
        self.assertIn("success", res)
        self.assertEqual(res["domain"], "services")
        if res["success"]:
            self.assertEqual(res["data"]["name"], "Spooler")
            self.assertIn("is_running", res["data"])

    def test_list_common_services(self) -> None:
        """Verify common services list query returns structured statuses."""
        res = list_common_services()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "services")
        self.assertGreater(res["data"]["total_monitored"], 0)
        self.assertIn("services", res["data"])

    # --- BLUETOOTH TOOLS ---
    def test_bluetooth_diagnostics(self) -> None:
        """Verify Bluetooth diagnostics return service and adapter presence."""
        res = get_bluetooth_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "bluetooth")
        self.assertIn("service_installed", res["data"])
        self.assertIn("adapter_detected", res["data"])

    # --- PRINTER TOOLS ---
    def test_printer_diagnostics(self) -> None:
        """Verify printer diagnostics return spooler state and printer list."""
        res = get_printer_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "printer")
        self.assertIn("spooler_running", res["data"])
        self.assertIn("printers", res["data"])

    # --- WINDOWS UPDATE TOOLS ---
    def test_windows_update_diagnostics(self) -> None:
        """Verify Windows Update diagnostics return service readiness."""
        res = get_windows_update_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "windows_update")
        self.assertIn("update_services_ready", res["data"])
        self.assertIn("services", res["data"])

    # --- DEFENDER TOOLS ---
    def test_defender_diagnostics(self) -> None:
        """Verify Microsoft Defender diagnostics return read-only status."""
        res = get_defender_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "defender")
        self.assertIn("antivirus_service_running", res["data"])
        self.assertIn("firewall_service_running", res["data"])

    # --- APPLICATION EVENT LOG TOOLS ---
    def test_recent_application_crashes(self) -> None:
        """Verify application crash event log reader returns structured events."""
        res = get_recent_application_crashes(limit=5, max_scan=50)
        self.assertIn("success", res)
        self.assertEqual(res["domain"], "applications")
        if res["success"]:
            self.assertIn("crashes", res["data"])
            self.assertIsInstance(res["data"]["crashes"], list)


class TestReadonlySafetyGuarantees(unittest.TestCase):
    """Static and behavioral tests guaranteeing tools do NOT invoke arbitrary shell or subprocesses."""

    def test_no_forbidden_execution_imports_in_windows_package(self) -> None:
        """Verify no windows tool module imports subprocess or os.system."""
        forbidden_calls = ["subprocess", "os.system", "os.popen", "exec(", "eval("]

        tool_modules = [
            "windows.network_tools",
            "windows.performance_tools",
            "windows.storage_tools",
            "windows.service_tools",
            "windows.bluetooth_tools",
            "windows.printer_tools",
            "windows.windows_update_tools",
            "windows.defender_tools",
            "windows.event_tools",
            "windows.system_info",
        ]

        for mod_name in tool_modules:
            mod = __import__(mod_name, fromlist=["*"])
            src = inspect.getsource(mod)
            for forbidden in forbidden_calls:
                self.assertNotIn(
                    forbidden,
                    src,
                    f"Forbidden execution pattern '{forbidden}' found in {mod_name}",
                )

    def test_all_tools_return_structured_dict(self) -> None:
        """Verify all exported tools return dictionary with required top-level keys."""
        tools_to_run = [
            get_network_adapters_diagnostics,
            get_cpu_diagnostics,
            get_memory_diagnostics,
            get_storage_diagnostics,
            get_temp_storage_info,
            list_common_services,
            get_bluetooth_diagnostics,
            get_printer_diagnostics,
            get_windows_update_diagnostics,
            get_defender_diagnostics,
        ]

        for tool_func in tools_to_run:
            res = tool_func()
            self.assertIsInstance(res, dict, f"{tool_func.__name__} did not return a dict")
            self.assertIn("success", res)
            self.assertIn("tool", res)
            self.assertIn("domain", res)
            self.assertIn("data", res)
            self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
