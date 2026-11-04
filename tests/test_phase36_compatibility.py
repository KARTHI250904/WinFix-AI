"""
WinFix AI — Phase 36 Real-World Windows Compatibility & Hardware Validation Test Suite.

Verifies:
- Live and simulated Windows OS, CPU, RAM, and storage compatibility
- Network, DNS, Windows Services, Windows Update, and Windows Defender inspection
- Bluetooth hardware presence and graceful absence handling
- Application crash diagnostics and WER event access
- Local AI (Ollama), Vision, and Voice STT degradation handling
- SQLite database integrity and permission boundary validation
- Privacy sanitization of EnvironmentSnapshot (0 passwords/tokens/private paths)
- Subsystem failure isolation and resource stability
- AST static security scan (0 prohibited execution calls)
Strictly adheres to: LLM != Windows Shell and UI != Execution Layer.
"""

import ast
import json
from pathlib import Path
import platform
import sys
import unittest
from unittest.mock import MagicMock, patch

from production.compatibility import (
    CompatibilityMatrix,
    CompatibilityStatus,
    ComponentCheck,
    EnvironmentSnapshot,
    ValidationType,
    WindowsCompatibilityValidator,
    default_compatibility_validator,
)


class TestWindowsEnvironmentCompatibility(unittest.TestCase):
    """Test suite for host OS, CPU, RAM, and Storage environment detection."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_validate_windows_os_real(self) -> None:
        """Verify Windows OS check produces valid structured result."""
        check = self.validator.validate_windows_os()
        self.assertEqual(check.component, "Windows OS")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))
        self.assertIn(check.validation_type, (ValidationType.REAL, ValidationType.SIMULATED))
        self.assertTrue(len(check.reason) > 5)

    def test_validate_windows_os_simulated_non_windows(self) -> None:
        """Non-Windows host simulation degrades gracefully."""
        check = self.validator.validate_windows_os(profile="NON_WINDOWS")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertEqual(check.validation_type, ValidationType.SIMULATED)
        self.assertIn("Non-Windows", check.reason)

    def test_validate_cpu_architecture(self) -> None:
        """Verify CPU core counts and architecture detection."""
        check = self.validator.validate_cpu_architecture()
        self.assertEqual(check.component, "CPU & Architecture")
        self.assertEqual(check.status, CompatibilityStatus.READY)
        self.assertIn("cores", check.detected_value.lower())

    def test_validate_memory_real(self) -> None:
        """Verify real system memory query returns valid capacity in GB."""
        check = self.validator.validate_memory()
        self.assertEqual(check.component, "System Memory")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))
        self.assertIn("GB RAM", check.detected_value)

    def test_validate_memory_low_ram_profile(self) -> None:
        """Simulated low RAM profile marks status as DEGRADED without crashing."""
        check = self.validator.validate_memory(profile="LOW_MEMORY")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertEqual(check.validation_type, ValidationType.SIMULATED)
        self.assertIn("critically low", check.reason)

    def test_validate_storage_filesystem_real(self) -> None:
        """Verify storage capacity check inspects system volume."""
        check = self.validator.validate_storage_filesystem()
        self.assertEqual(check.component, "Storage & Filesystem")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))
        self.assertIn("GB Free", check.detected_value)

    def test_validate_storage_disk_full_profile(self) -> None:
        """Simulated disk-full profile triggers safe minimal-write fallback."""
        check = self.validator.validate_storage_filesystem(profile="DISK_FULL")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertEqual(check.validation_type, ValidationType.SIMULATED)
        self.assertIn("Full", check.detected_value)


class TestHardwareSubsystemCompatibility(unittest.TestCase):
    """Test suite for Network, DNS, Services, Windows Update, Defender, and Bluetooth."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_validate_network_adapters_real(self) -> None:
        """Verify network adapter inspection without modifying network configuration."""
        check = self.validator.validate_network_adapters()
        self.assertEqual(check.component, "Network Adapters")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_validate_network_adapters_no_network_profile(self) -> None:
        """No network adapters profile marks UNAVAILABLE gracefully."""
        check = self.validator.validate_network_adapters(profile="NO_NETWORK")
        self.assertEqual(check.status, CompatibilityStatus.UNAVAILABLE)
        self.assertIn("Airplane mode", check.reason)

    def test_validate_dns_diagnostics_real(self) -> None:
        """Verify DNS diagnostic check executes safely."""
        check = self.validator.validate_dns_diagnostics()
        self.assertEqual(check.component, "DNS Diagnostics")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_validate_dns_diagnostics_failure_profile(self) -> None:
        """DNS failure profile correctly detects resolution failure."""
        check = self.validator.validate_dns_diagnostics(profile="DNS_FAIL")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertIn("DNS resolution failed", check.reason)

    def test_validate_windows_services_real(self) -> None:
        """Verify Windows Services inspection queries common service list."""
        check = self.validator.validate_windows_services()
        self.assertEqual(check.component, "Windows Services")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_validate_windows_update_real(self) -> None:
        """Verify Windows Update inspection checks wuauserv state."""
        check = self.validator.validate_windows_update()
        self.assertEqual(check.component, "Windows Update")
        self.assertIn("wuauserv Status", check.detected_value)

    def test_validate_windows_defender_real(self) -> None:
        """Verify Windows Defender inspection checks WinDefend status."""
        check = self.validator.validate_windows_defender()
        self.assertEqual(check.component, "Windows Defender")
        self.assertIn("WinDefend Status", check.detected_value)

    def test_validate_bluetooth_real(self) -> None:
        """Verify Bluetooth inspection handles both present and absent hardware."""
        check = self.validator.validate_bluetooth()
        self.assertEqual(check.component, "Bluetooth Subsystem")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.UNAVAILABLE))

    def test_validate_bluetooth_absence_profile(self) -> None:
        """Absence of Bluetooth hardware is marked UNAVAILABLE, not an error."""
        check = self.validator.validate_bluetooth(profile="NO_BLUETOOTH")
        self.assertEqual(check.status, CompatibilityStatus.UNAVAILABLE)
        self.assertIn("No Bluetooth Adapter Present", check.detected_value)

    def test_validate_application_crashes_real(self) -> None:
        """Verify WER application crash log query capability."""
        check = self.validator.validate_application_crashes()
        self.assertEqual(check.component, "Application Crash Diagnostics")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))


class TestLocalAIAndMultimodalCompatibility(unittest.TestCase):
    """Test suite for Ollama, Vision, and Speech-to-Text compatibility."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_validate_ollama_real(self) -> None:
        """Verify Ollama service inspection."""
        check = self.validator.validate_ollama_local_ai()
        self.assertEqual(check.component, "Local AI (Ollama)")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_validate_ollama_offline_profile(self) -> None:
        """Offline Ollama profile triggers deterministic fallback gracefully."""
        check = self.validator.validate_ollama_local_ai(profile="OFFLINE_AI")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertIn("Ollama Offline", check.detected_value)

    def test_validate_vision_model_real(self) -> None:
        """Verify screenshot vision model readiness."""
        check = self.validator.validate_vision_model()
        self.assertEqual(check.component, "Vision Diagnostics")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_validate_vision_unavailable_profile(self) -> None:
        """Unavailable vision profile triggers text-mode fallback."""
        check = self.validator.validate_vision_model(profile="VISION_UNAVAILABLE")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertIn("Vision Model Offline", check.detected_value)

    def test_validate_voice_stt_real(self) -> None:
        """Verify speech recognition transcriber readiness."""
        check = self.validator.validate_voice_stt()
        self.assertEqual(check.component, "Voice Diagnostics (STT)")
        self.assertIn(check.status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_validate_voice_unavailable_profile(self) -> None:
        """Unavailable STT profile triggers text input fallback."""
        check = self.validator.validate_voice_stt(profile="VOICE_UNAVAILABLE")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertIn("STT Engine Unavailable", check.detected_value)


class TestDatabaseAndPermissionsCompatibility(unittest.TestCase):
    """Test suite for SQLite storage and administrative privilege inspection."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_validate_sqlite_database_real(self) -> None:
        """Verify SQLite database connection and table integrity."""
        check = self.validator.validate_sqlite_database()
        self.assertEqual(check.component, "SQLite Storage")
        self.assertEqual(check.status, CompatibilityStatus.READY)
        self.assertIn("SQLite Active", check.detected_value)

    def test_validate_sqlite_database_degraded_profile(self) -> None:
        """Degraded database profile switches to ephemeral memory store."""
        check = self.validator.validate_sqlite_database(profile="DEGRADED_DATABASE")
        self.assertEqual(check.status, CompatibilityStatus.DEGRADED)
        self.assertIn("Read-Only", check.detected_value)

    def test_validate_permissions_uac_real(self) -> None:
        """Verify process elevation detection."""
        check = self.validator.validate_permissions_uac()
        self.assertEqual(check.component, "User Permissions")
        self.assertEqual(check.status, CompatibilityStatus.READY)
        self.assertIn("Elevated", check.detected_value)

    def test_validate_permissions_limited_profile(self) -> None:
        """Standard non-elevated user is handled with clear notification."""
        check = self.validator.validate_permissions_uac(profile="LIMITED_PERMISSIONS")
        self.assertEqual(check.status, CompatibilityStatus.READY)
        self.assertIn("Standard User", check.detected_value)


class TestEnvironmentSnapshotAndPrivacy(unittest.TestCase):
    """Test suite ensuring environment snapshots are non-sensitive and strictly sanitized."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_generate_environment_snapshot(self) -> None:
        """Verify environment snapshot constructs complete typed metadata."""
        snapshot = self.validator.generate_environment_snapshot()
        self.assertIsInstance(snapshot, EnvironmentSnapshot)
        self.assertTrue(len(snapshot.os_name) > 0)
        self.assertGreater(snapshot.total_ram_gb, 0.0)
        self.assertGreater(snapshot.cpu_count_logical, 0)
        self.assertTrue(snapshot.app_version.startswith("1.0"))

    def test_environment_snapshot_privacy_sanitization(self) -> None:
        """Environment snapshot must NOT contain passwords, auth tokens, or private paths."""
        snapshot = self.validator.generate_environment_snapshot()
        raw_json = json.dumps(snapshot.to_dict()).lower()

        forbidden_keys = ["password", "token", "secret", "bearer", "private_key", "c:\\users\\"]
        for key in forbidden_keys:
            self.assertNotIn(key, raw_json, f"Private/sensitive token '{key}' found in snapshot")


class TestFailureIsolationAndGracefulDegradation(unittest.TestCase):
    """Test suite verifying subsystem failures remain fully isolated."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_failure_isolation_evaluation(self) -> None:
        """Isolated failures do not cascade to unrelated subsystems."""
        iso_results = self.validator.evaluate_failure_isolation()
        self.assertTrue(iso_results["bluetooth_absence_isolated"])
        self.assertTrue(iso_results["ollama_absence_isolated"])
        self.assertTrue(iso_results["network_absence_isolated"])
        self.assertTrue(iso_results["overall_graceful_degradation"])

    def test_overall_compatibility_matrix_operational(self) -> None:
        """Complete compatibility matrix is operational under normal and degraded profiles."""
        matrix = self.validator.validate_environment()
        self.assertTrue(matrix.is_operational())
        self.assertIn(matrix.overall_status, (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED))

    def test_matrix_to_dict_structure(self) -> None:
        """CompatibilityMatrix serializes cleanly to dictionary."""
        matrix = self.validator.validate_environment()
        d = matrix.to_dict()
        self.assertIn("overall_status", d)
        self.assertIn("checks", d)
        self.assertIn("snapshot", d)
        self.assertIsInstance(d["checks"], dict)


class TestPhase36PredefinedProfilesAndEnums(unittest.TestCase):
    """Test suite verifying all predefined simulation profiles and enum definitions."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_all_predefined_profiles_evaluation(self) -> None:
        """Verify each predefined simulation profile evaluates cleanly without exceptions."""
        profiles = [
            "FULLY_AVAILABLE",
            "OFFLINE_AI",
            "NO_BLUETOOTH",
            "NO_NETWORK",
            "LIMITED_PERMISSIONS",
            "PARTIAL_HARDWARE",
            "DEGRADED_DATABASE",
            "OLLAMA_UNAVAILABLE",
            "VISION_UNAVAILABLE",
            "VOICE_UNAVAILABLE",
            "NON_WINDOWS",
            "LOW_MEMORY",
            "DISK_FULL",
            "DNS_FAIL",
        ]
        for p in profiles:
            matrix = self.validator.validate_environment(profile=p)
            self.assertIsInstance(matrix, CompatibilityMatrix)
            self.assertTrue(len(matrix.checks) >= 15)
            self.assertTrue(matrix.is_operational())

    def test_compatibility_status_enum_values(self) -> None:
        """Verify all CompatibilityStatus values."""
        self.assertEqual(CompatibilityStatus.READY.value, "READY")
        self.assertEqual(CompatibilityStatus.DEGRADED.value, "DEGRADED")
        self.assertEqual(CompatibilityStatus.UNAVAILABLE.value, "UNAVAILABLE")
        self.assertEqual(CompatibilityStatus.BLOCKED.value, "BLOCKED")
        self.assertEqual(CompatibilityStatus.UNKNOWN.value, "UNKNOWN")
        self.assertEqual(CompatibilityStatus.NOT_TESTED.value, "NOT_TESTED")

    def test_validation_type_enum_values(self) -> None:
        """Verify all ValidationType values."""
        self.assertEqual(ValidationType.REAL.value, "REAL")
        self.assertEqual(ValidationType.SIMULATED.value, "SIMULATED")
        self.assertEqual(ValidationType.STATIC.value, "STATIC")
        self.assertEqual(ValidationType.UNTESTED.value, "UNTESTED")

    def test_component_check_to_dict(self) -> None:
        """ComponentCheck serializes properly to dictionary."""
        chk = ComponentCheck(
            component="Test Subsystem",
            detected_value="Val",
            expected_capability="Cap",
            status=CompatibilityStatus.READY,
            validation_type=ValidationType.REAL,
            reason="Good",
            impact="None",
            safe_fallback="N/A",
        )
        d = chk.to_dict()
        self.assertEqual(d["component"], "Test Subsystem")
        self.assertEqual(d["status"], "READY")
        self.assertEqual(d["validation_type"], "REAL")

    def test_default_compatibility_validator_instance(self) -> None:
        """Verify default_compatibility_validator is initialized and operational."""
        self.assertIsInstance(default_compatibility_validator, WindowsCompatibilityValidator)


class TestResourceStability(unittest.TestCase):
    """Test suite ensuring repeated compatibility evaluation does not leak memory."""

    def setUp(self) -> None:
        self.validator = WindowsCompatibilityValidator()

    def test_repeated_compatibility_checks_stability(self) -> None:
        """10 repeated cycles must maintain stable memory with delta < 50 MB."""
        stability = self.validator.evaluate_resource_stability(iterations=10)
        self.assertEqual(stability["iterations"], 10)
        self.assertTrue(stability["is_stable"], f"Memory leaked: {stability['memory_delta_mb']} MB delta")


class TestPhase36StaticSecurityAST(unittest.TestCase):
    """AST static security scan verifying compatibility module contains ZERO prohibited calls."""

    FORBIDDEN_CALLS = {
        "subprocess",
        "os.system",
        "os.popen",
        "Popen",
        "CreateProcess",
        "WinExec",
        "ShellExecute",
    }

    def test_ast_scan_compatibility_file(self) -> None:
        """Verify production/compatibility.py contains 0 forbidden execution calls."""
        project_root = Path(__file__).resolve().parent.parent
        compat_file = project_root / "production" / "compatibility.py"
        self.assertTrue(compat_file.exists(), f"File {compat_file} does not exist.")

        tree = ast.parse(compat_file.read_text(encoding="utf-8"), filename=str(compat_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(
                        node.func.id,
                        {"eval", "exec"},
                        f"Prohibited built-in {node.func.id} in compatibility.py:L{node.lineno}",
                    )
                elif isinstance(node.func, ast.Attribute):
                    attr_chain = []
                    curr = node.func
                    while isinstance(curr, ast.Attribute):
                        attr_chain.append(curr.attr)
                        curr = curr.value
                    if isinstance(curr, ast.Name):
                        attr_chain.append(curr.id)
                    full_call = ".".join(reversed(attr_chain))
                    call_parts = full_call.split(".")
                    for forbidden in self.FORBIDDEN_CALLS:
                        self.assertNotIn(
                            forbidden,
                            call_parts,
                            f"Prohibited execution call '{full_call}' in compatibility.py:L{node.lineno}",
                        )


if __name__ == "__main__":
    unittest.main()
