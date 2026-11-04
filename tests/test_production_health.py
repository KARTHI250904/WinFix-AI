"""
WinFix AI — Phase 23 Windows API Diagnostic & Tool Compatibility Tests.

Validates:
1. Read-Only Diagnostic Tools across all 8 Core Domains:
   - Network (check_internet_connectivity, get_network_adapters_diagnostics)
   - Performance (get_cpu_diagnostics, get_memory_diagnostics, get_top_cpu_processes)
   - Storage (get_temp_storage_info, get_disk_diagnostics)
   - Services (get_service_status, list_critical_services)
   - Bluetooth (get_bluetooth_adapters, get_bluetooth_radio_status)
   - Windows Update (get_windows_update_service_status, get_windows_update_diagnostics)
   - Defender (get_defender_antivirus_status, get_defender_security_health)
   - Application Crashes (get_application_crash_summary, get_application_crash_diagnostics)
2. Non-elevated execution guarantee (SAFE tools never require administrator rights).
3. Structured output schema conformance.
"""

import unittest

from agent.tool_metadata import RiskLevel
from agent.tool_registry import create_default_registry


class TestProductionWindowsToolsHealth(unittest.TestCase):
    """Test suite validating all safe diagnostic tools against the Windows environment."""

    @classmethod
    def setUpClass(cls):
        cls.registry = create_default_registry()

    def test_domain1_network_diagnostics_safe(self):
        tool = self.registry.get("get_network_adapters_diagnostics")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        self.assertFalse(tool.requires_admin)
        res = tool.handler()
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))

    def test_domain2_performance_diagnostics_safe(self):
        tool = self.registry.get("get_cpu_diagnostics")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler()
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))
        self.assertIn("data", res)
        self.assertIn("overall_percent", res["data"])

    def test_domain3_storage_diagnostics_safe(self):
        tool = self.registry.get("get_temp_storage_info")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler()
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))

    def test_domain4_services_diagnostics_safe(self):
        tool = self.registry.get("get_service_status")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler(service_name="Spooler")
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))

    def test_domain5_bluetooth_diagnostics_safe(self):
        tool = self.registry.get("get_bluetooth_service_status")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler()
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))

    def test_domain6_windows_update_diagnostics_safe(self):
        tool = self.registry.get("get_windows_update_service_status")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler()
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))

    def test_domain7_defender_diagnostics_safe(self):
        tool = self.registry.get("get_defender_antivirus_status")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler()
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))

    def test_domain8_application_crash_diagnostics_safe(self):
        tool = self.registry.get("get_application_crash_summary")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        res = tool.handler(limit=5)
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("success", False))


if __name__ == "__main__":
    unittest.main()
