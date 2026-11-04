"""
WinFix AI — Phase 23 Windows Environment Detection Tests.

Validates:
1. Environment Telemetry Detection (OS, build, architecture, Python version).
2. Hardware & Resource Metrics (RAM, CPU core detection).
3. Process Elevation & Privilege Detection.
4. Privacy Sanitization of User Paths & Host Telemetry.
"""

from pathlib import Path
import platform
import unittest
from unittest.mock import MagicMock, patch

from production.config import ProductionConfig
from production.environment import (
    WindowsEnvironmentInfo,
    detect_windows_environment,
    is_process_elevated,
)
from production.paths import resolve_app_paths


class TestWindowsEnvironmentDetection(unittest.TestCase):
    """Test suite for environment detection and telemetry sanitization."""

    def test_detect_windows_environment_structure(self):
        env = detect_windows_environment()
        self.assertIsInstance(env, WindowsEnvironmentInfo)
        self.assertEqual(env.os_name, platform.system())
        self.assertTrue(bool(env.python_version))
        self.assertGreater(env.total_ram_gb, 0.0)
        self.assertGreaterEqual(env.cpu_count_logical, 1)
        self.assertTrue(env.sqlite_available)

    def test_environment_telemetry_sanitization(self):
        fake_paths = resolve_app_paths(base_data_dir=Path("C:/Users/JohnDoe/AppData/Local/WinFixAI"))
        cfg = ProductionConfig(paths=fake_paths)
        env = detect_windows_environment(cfg)

        self.assertNotIn("JohnDoe", env.app_data_path)
        self.assertIn("C:\\Users\\<User>\\AppData\\Local\\WinFixAI", env.app_data_path)

    def test_elevation_check(self):
        # Verify boolean return without crashing
        is_elevated = is_process_elevated()
        self.assertIsInstance(is_elevated, bool)

    def test_mocked_elevation_override(self):
        with patch.dict("os.environ", {"WINFIX_MOCK_ADMIN": "true"}):
            with patch("ctypes.windll.shell32.IsUserAnAdmin", side_effect=AttributeError):
                self.assertTrue(is_process_elevated())


if __name__ == "__main__":
    unittest.main()
