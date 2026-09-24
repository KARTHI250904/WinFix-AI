"""Tests for WinFix AI read-only system information collector."""

import unittest
from unittest.mock import patch

from windows.system_info import (
    _format_bytes,
    _format_seconds,
    get_complete_system_info,
    get_computer_info,
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_network_adapters_info,
    get_os_info,
    get_uptime_info,
)


class TestSystemInfo(unittest.TestCase):
    """Test suite for system_info module."""

    def test_complete_system_info_structure(self) -> None:
        """Verify complete system info contains all expected top-level keys."""
        info = get_complete_system_info()
        expected_keys = {
            "timestamp",
            "os",
            "computer",
            "cpu",
            "memory",
            "disk",
            "network",
            "uptime",
        }
        self.assertTrue(expected_keys.issubset(info.keys()))

    def test_os_info_structure(self) -> None:
        """Verify OS collector returns valid fields."""
        os_info = get_os_info()
        self.assertIn(os_info["status"], ["available", "unavailable"])
        self.assertIn("name", os_info)
        self.assertIn("release", os_info)
        self.assertIn("edition", os_info)
        self.assertIn("build_number", os_info)
        self.assertIn("architecture", os_info)
        self.assertIn("is_windows", os_info)

    def test_computer_info_structure(self) -> None:
        """Verify computer identity collector returns valid fields."""
        comp_info = get_computer_info()
        self.assertIn(comp_info["status"], ["available", "unavailable"])
        self.assertIn("computer_name", comp_info)
        self.assertIn("username", comp_info)
        self.assertIn("system_root", comp_info)
        self.assertIn("system_drive", comp_info)

    def test_cpu_info_structure(self) -> None:
        """Verify CPU collector returns valid fields."""
        cpu_info = get_cpu_info()
        self.assertIn(cpu_info["status"], ["available", "unavailable"])
        self.assertIn("model", cpu_info)
        self.assertIn("physical_cores", cpu_info)
        self.assertIn("logical_threads", cpu_info)
        self.assertIn("architecture", cpu_info)
        if cpu_info["status"] == "available":
            self.assertGreater(cpu_info["logical_threads"], 0)

    def test_memory_info_structure(self) -> None:
        """Verify memory collector returns valid fields and formatted strings."""
        mem_info = get_memory_info()
        self.assertIn(mem_info["status"], ["available", "unavailable"])
        self.assertIn("total_bytes", mem_info)
        self.assertIn("total_formatted", mem_info)
        self.assertIn("available_bytes", mem_info)
        self.assertIn("available_formatted", mem_info)
        self.assertIn("percent_used", mem_info)
        if mem_info["status"] == "available":
            self.assertGreater(mem_info["total_bytes"], 0)
            self.assertGreaterEqual(mem_info["percent_used"], 0.0)

    def test_disk_info_structure(self) -> None:
        """Verify disk collector returns drive details and system drive information."""
        disk_info = get_disk_info()
        self.assertIn(disk_info["status"], ["available", "unavailable"])
        self.assertIn("drives_count", disk_info)
        self.assertIn("drives", disk_info)
        self.assertIn("system_drive", disk_info)
        if disk_info["status"] == "available" and disk_info["drives_count"] > 0:
            first_drive = disk_info["drives"][0]
            self.assertIn("device", first_drive)
            self.assertIn("mountpoint", first_drive)
            self.assertIn("total_formatted", first_drive)
            self.assertIn("free_formatted", first_drive)

    def test_network_adapters_info_structure(self) -> None:
        """Verify network adapter collector returns adapter list."""
        net_info = get_network_adapters_info()
        self.assertIn(net_info["status"], ["available", "unavailable"])
        self.assertIn("total_adapters_count", net_info)
        self.assertIn("adapters", net_info)
        self.assertIn("active_adapters", net_info)

    def test_uptime_info_structure(self) -> None:
        """Verify uptime collector returns formatted duration."""
        uptime_info = get_uptime_info()
        self.assertIn(uptime_info["status"], ["available", "unavailable"])
        self.assertIn("uptime_seconds", uptime_info)
        self.assertIn("uptime_formatted", uptime_info)
        self.assertIn("boot_time_formatted", uptime_info)
        if uptime_info["status"] == "available":
            self.assertGreater(uptime_info["uptime_seconds"], 0)

    def test_resilience_to_subsystem_failure(self) -> None:
        """Verify that an unexpected exception in one collector does not break get_complete_system_info."""
        with patch("windows.system_info.get_cpu_info", side_effect=RuntimeError("Simulated CPU Failure")):
            info = get_complete_system_info()
            # CPU should fail, but OS, memory, and disk must still be collected
            self.assertIn("os", info)
            self.assertIn("memory", info)
            self.assertIn("disk", info)
            self.assertEqual(info["os"]["status"], "available")
            self.assertEqual(info["memory"]["status"], "available")

    def test_format_helpers(self) -> None:
        """Verify byte and duration format helper functions."""
        self.assertEqual(_format_bytes(1024), "1.00 KB")
        self.assertEqual(_format_bytes(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(_format_bytes(None), "Unknown")

        self.assertIn("1 day", _format_seconds(86400))
        self.assertIn("2 hours", _format_seconds(7200))
        self.assertEqual(_format_seconds(None), "Unknown")


if __name__ == "__main__":
    unittest.main()
