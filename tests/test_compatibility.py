"""
WinFix AI — Phase 23 Compatibility Matrix & Capability Tests.

Validates:
1. CompatibilityValidator Matrix Generation.
2. Capability status evaluation (READY, DEGRADED, UNAVAILABLE, BLOCKED).
3. Graceful degradation when optional components (Ollama, Vision, Voice) are unavailable.
4. Core system operational invariant checks.
"""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from production.config import ProductionConfig
from production.environment import (
    CapabilityEntry,
    CapabilityMatrix,
    CapabilityStatus,
    CompatibilityValidator,
    WindowsEnvironmentInfo,
)
from production.paths import resolve_app_paths
from production.setup import run_first_time_setup


class TestCompatibilityValidator(unittest.TestCase):
    """Test suite for CompatibilityValidator and CapabilityMatrix."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_compat_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)
        self.config = ProductionConfig(paths=self.paths)
        run_first_time_setup(self.config)
        self.validator = CompatibilityValidator(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_full_compatibility_matrix(self):
        matrix, env = self.validator.validate()
        self.assertIsInstance(matrix, CapabilityMatrix)
        self.assertIsInstance(env, WindowsEnvironmentInfo)

        # Core layers must be operational
        self.assertTrue(matrix.is_operational())
        self.assertEqual(matrix.app_storage.status, CapabilityStatus.READY)
        self.assertEqual(matrix.sqlite_storage.status, CapabilityStatus.READY)
        self.assertEqual(matrix.tool_registry.status, CapabilityStatus.READY)
        self.assertEqual(matrix.safety_engine.status, CapabilityStatus.READY)

    def test_matrix_to_dict_serialization(self):
        matrix, _ = self.validator.validate()
        d = matrix.to_dict()
        self.assertIn("core_system", d)
        self.assertIn("tool_registry", d)
        self.assertIn("safety_engine", d)
        self.assertEqual(d["tool_registry"]["status"], "READY")

    def test_degraded_ollama_does_not_block_operation(self):
        with patch("production.environment.detect_windows_environment") as mock_detect:
            mock_detect.return_value = WindowsEnvironmentInfo(
                os_name="Windows",
                os_version="10.0.22631",
                os_release="11",
                os_build="22631",
                os_architecture="AMD64",
                python_version="3.12.0",
                app_version="1.0.0",
                is_admin=False,
                total_ram_gb=16.0,
                available_ram_gb=8.0,
                cpu_count_logical=8,
                cpu_count_physical=4,
                app_data_path="C:\\Users\\<User>\\AppData\\Local\\WinFixAI",
                temp_dir_path="C:\\Users\\<User>\\AppData\\Local\\WinFixAI\\Temp",
                sqlite_available=True,
                ollama_available=False,  # Ollama offline
                ai_model_available=False,
                vision_available=True,
                voice_available=True,
            )
            matrix, _ = self.validator.validate()
            self.assertEqual(matrix.ollama_service.status, CapabilityStatus.DEGRADED)
            self.assertEqual(matrix.ai_model.status, CapabilityStatus.UNAVAILABLE)
            # System remains operational via deterministic heuristics
            self.assertTrue(matrix.is_operational())


if __name__ == "__main__":
    unittest.main()
