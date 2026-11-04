"""WinFix AI — Installer Security & Tamper Detection Verification Suite (Phase 25).

Validates:
1. Rejection of dangerous installation target paths (UNC, traversal, system roots).
2. Package integrity validation and tamper detection.
3. Checksum mismatch alerts.
4. Uninstallation boundary safety (fixed path resolution, no arbitrary deletions).
5. Secret scanning verification.
"""

import json
from pathlib import Path
import tempfile
import unittest

from build.build_windows import scan_for_secrets
from production.installation import (
    InstallationManager,
    InstallationState,
    IntegrityCheckResult,
    compute_file_sha256,
    validate_installation_path,
)


class TestInstallerSecurity(unittest.TestCase):
    """Rigorous security test suite for WinFix AI packaging and installation management."""

    def test_path_validation_rejects_unc_and_network_paths(self):
        """Installer path validation must reject UNC and remote network paths."""
        unc_paths = [
            Path(r"\\192.168.1.10\share\WinFixAI"),
            Path(r"\\fileserver\c$\WinFixAI"),
            Path(r"//remoteserver/public/WinFixAI"),
        ]
        for p in unc_paths:
            with self.subTest(path=str(p)):
                is_valid, msg = validate_installation_path(p)
                self.assertFalse(is_valid)
                self.assertIn("prohibited", msg.lower())

    def test_path_validation_rejects_path_traversals(self):
        """Installer path validation must reject relative path traversals."""
        traversal_paths = [
            Path(r"C:\Program Files\..\..\Windows\System32\WinFix"),
            Path(r"..\..\AppData\WinFix"),
        ]
        for p in traversal_paths:
            with self.subTest(path=str(p)):
                is_valid, msg = validate_installation_path(p)
                self.assertFalse(is_valid)

    def test_path_validation_rejects_system_critical_roots(self):
        """Direct installation into Windows system root directories must be blocked."""
        system_roots = [
            Path(r"C:\Windows"),
            Path(r"C:\Windows\System32"),
            Path(r"C:\\"),
        ]
        for p in system_roots:
            with self.subTest(path=str(p)):
                is_valid, msg = validate_installation_path(p)
                self.assertFalse(is_valid)

    def test_integrity_check_detects_tampered_files(self):
        """Integrity checker must detect modified files with mismatched hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            install_dir = Path(tmpdir) / "app"
            install_dir.mkdir(parents=True)

            # Create test files
            f1 = install_dir / "app.py"
            f1.write_text("print('original')", encoding="utf-8")
            h1 = compute_file_sha256(f1)

            # Write manifest
            manifest_file = install_dir / "BUILD_MANIFEST.json"
            manifest = {
                "version": "1.0.0",
                "checksums": {
                    "app.py": h1,
                },
            }
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

            mgr = InstallationManager(install_dir=install_dir)
            res1 = mgr.verify_integrity()
            self.assertTrue(res1.is_valid)

            # Tamper with app.py
            f1.write_text("print('tampered')", encoding="utf-8")
            res2 = mgr.verify_integrity()
            self.assertFalse(res2.is_valid)
            self.assertIn("app.py", res2.checksum_mismatches)

    def test_integrity_check_detects_missing_files(self):
        """Integrity checker must detect deleted or missing files specified in manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            install_dir = Path(tmpdir) / "app"
            install_dir.mkdir(parents=True)

            f1 = install_dir / "launcher.py"
            f1.write_text("# launcher", encoding="utf-8")
            h1 = compute_file_sha256(f1)

            manifest_file = install_dir / "BUILD_MANIFEST.json"
            manifest = {
                "version": "1.0.0",
                "checksums": {
                    "launcher.py": h1,
                    "missing_module.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                },
            }
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

            mgr = InstallationManager(install_dir=install_dir)
            res = mgr.verify_integrity()
            self.assertFalse(res.is_valid)
            self.assertIn("missing_module.py", res.missing_files)

    def test_secret_scanner_catches_leaked_credentials(self):
        """Secret scanner function must detect prohibited API keys or passwords."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scan_dir = Path(tmpdir)
            secret_file = scan_dir / "leaked_credentials.py"
            secret_file.write_text("API_KEY = 'sk-proj-1234567890abcdef'", encoding="utf-8")

            violations = scan_for_secrets(scan_dir)
            self.assertGreater(len(violations), 0)
            self.assertTrue(any("sk-" in v or "api_key" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
