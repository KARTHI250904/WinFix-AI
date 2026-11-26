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
from production.paths import AppPaths, initialize_app_directories, is_safe_app_path, resolve_app_paths


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

    def test_wf_sec_01_launcher_loopback_validation(self):
        """WF-SEC-01: Launcher validate_host_address must allow loopback and reject all non-loopback hosts."""
        from winfix_launcher import ALLOWED_LOOPBACK_HOSTS, launch_streamlit_app, validate_host_address

        self.assertIn("127.0.0.1", ALLOWED_LOOPBACK_HOSTS)
        self.assertIn("localhost", ALLOWED_LOOPBACK_HOSTS)

        # Loopback hosts must be allowed
        for valid_host in ["127.0.0.1", "localhost", "LOCALHOST", " 127.0.0.1 "]:
            with self.subTest(host=valid_host):
                ok, err = validate_host_address(valid_host)
                self.assertTrue(ok)
                self.assertEqual(err, "")

        # Unsafe hosts must be rejected
        unsafe_hosts = ["0.0.0.0", "192.168.1.1", "10.0.0.5", "172.16.0.1", "::", "::1", "", None, "evil.com"]
        for bad_host in unsafe_hosts:
            with self.subTest(host=bad_host):
                ok, err = validate_host_address(bad_host)
                self.assertFalse(ok)
                self.assertTrue(
                    "prohibited" in err.lower() or "empty" in err.lower() or "invalid" in err.lower(),
                    f"Unexpected error message: {err}",
                )

        # launch_streamlit_app must fail closed when given an unsafe host
        ret = launch_streamlit_app(host="0.0.0.0")
        self.assertEqual(ret, 1)

    def test_wf_sec_01_packaged_distribution_and_streamlit_config_integrity(self):
        """WF-SEC-01: Rebuilt distribution must contain identical launcher and loopback .streamlit config."""
        root_dir = Path(__file__).resolve().parent.parent
        dist_dir = root_dir / "build" / "dist" / "WinFixAI"
        root_launcher = root_dir / "winfix_launcher.py"
        packaged_launcher = dist_dir / "winfix_launcher.py"
        packaged_streamlit_cfg = dist_dir / ".streamlit" / "config.toml"
        iss_file = root_dir / "build" / "artifacts" / "winfix_setup.iss"

        # 1. Packaged launcher must exist and match root launcher exactly
        self.assertTrue(dist_dir.exists(), "build/dist/WinFixAI directory must exist")
        self.assertTrue(packaged_launcher.exists(), "Packaged winfix_launcher.py must exist")
        self.assertEqual(
            compute_file_sha256(root_launcher),
            compute_file_sha256(packaged_launcher),
            "Packaged launcher hash must match authoritative root launcher",
        )

        # 2. Packaged launcher must not contain default 0.0.0.0
        packaged_content = packaged_launcher.read_text(encoding="utf-8")
        self.assertNotIn('default="0.0.0.0"', packaged_content)
        self.assertIn('default="127.0.0.1"', packaged_content)

        # 3. Packaged .streamlit/config.toml must exist and enforce loopback address
        self.assertTrue(packaged_streamlit_cfg.exists(), "Packaged .streamlit/config.toml must exist")
        cfg_content = packaged_streamlit_cfg.read_text(encoding="utf-8")
        self.assertIn('address = "127.0.0.1"', cfg_content)
        self.assertNotIn('address = "0.0.0.0"', cfg_content)
        self.assertIn("gatherUsageStats = false", cfg_content)

        # 4. Inno setup script must package the rebuilt distribution
        self.assertTrue(iss_file.exists(), "winfix_setup.iss must exist")
        iss_content = iss_file.read_text(encoding="utf-8")
        self.assertIn(r"build/dist/WinFixAI\*", iss_content)
        self.assertNotIn("0.0.0.0", iss_content)

    def test_wf_sec_04_sibling_prefix_collision_rejected(self):
        """WF-SEC-04: is_safe_app_path must reject sibling directories/files sharing prefix with allowed root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            allowed_root = base_dir / "WinFixApp"
            allowed_root.mkdir(parents=True, exist_ok=True)

            # Sibling directory starting with allowed_root prefix
            sibling_dir = base_dir / "WinFixApp_Malicious"
            sibling_dir.mkdir(parents=True, exist_ok=True)
            sibling_file = sibling_dir / "leak.txt"
            sibling_file.write_text("leak", encoding="utf-8")

            # Sibling file sharing directory prefix
            sibling_direct_file = base_dir / "WinFixApp.bak"
            sibling_direct_file.write_text("backup", encoding="utf-8")

            # Sub-level sibling collision
            data_dir = allowed_root / "Data"
            data_dir.mkdir(parents=True, exist_ok=True)
            data_sibling = allowed_root / "Data_Exploit"
            data_sibling.mkdir(parents=True, exist_ok=True)

            # Assert all sibling collisions are strictly rejected
            self.assertFalse(is_safe_app_path(sibling_file, allowed_root))
            self.assertFalse(is_safe_app_path(sibling_dir, allowed_root))
            self.assertFalse(is_safe_app_path(sibling_direct_file, allowed_root))
            self.assertFalse(is_safe_app_path(data_sibling, data_dir))

    def test_wf_sec_04_path_traversal_variations_rejected(self):
        """WF-SEC-04: is_safe_app_path must reject dot-dot traversal escaping the root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_root = Path(tmpdir) / "app_root"
            allowed_root.mkdir(parents=True, exist_ok=True)

            traversal_escapes = [
                allowed_root / ".." / "outside.txt",
                allowed_root / "sub" / ".." / ".." / "outside.txt",
                allowed_root / ".." / ".." / "Windows" / "System32" / "cmd.exe",
                allowed_root / ".." / "app_root_sibling" / "secret.json",
                allowed_root / "sub" / ".." / ".." / "app_root_sibling" / "secret.json",
                Path(r"..\..\..\etc\passwd"),
            ]
            for t in traversal_escapes:
                with self.subTest(traversal=str(t)):
                    self.assertFalse(is_safe_app_path(t, allowed_root))

    def test_wf_sec_04_absolute_paths_outside_root_rejected(self):
        """WF-SEC-04: is_safe_app_path must reject absolute paths residing outside the allowed root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_root = Path(tmpdir) / "app_root"
            allowed_root.mkdir(parents=True, exist_ok=True)

            outside_paths = [
                Path("C:/Windows/System32"),
                Path("C:/Windows/System32/drivers/etc/hosts"),
                Path("C:/Users/Public/malicious.exe"),
                Path("C:/Program Files/WinFixAI"),
                Path("C:/"),
            ]
            for p in outside_paths:
                with self.subTest(outside_path=str(p)):
                    self.assertFalse(is_safe_app_path(p, allowed_root))

    def test_wf_sec_04_valid_nested_and_normalized_paths_accepted(self):
        """WF-SEC-04: is_safe_app_path must accept valid children, nested paths, and internal traversals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_root = Path(tmpdir) / "app_root"
            allowed_root.mkdir(parents=True, exist_ok=True)

            # Allowed root itself
            self.assertTrue(is_safe_app_path(allowed_root, allowed_root))

            # Direct child
            child = allowed_root / "Data"
            self.assertTrue(is_safe_app_path(child, allowed_root))

            # Deep nested file
            deep_file = allowed_root / "Data" / "reports" / "2026" / "summary.json"
            self.assertTrue(is_safe_app_path(deep_file, allowed_root))

            # Internal traversal that stays strictly within the root
            internal_traversal = allowed_root / "Data" / "sub" / ".." / "reports" / "summary.json"
            self.assertTrue(is_safe_app_path(internal_traversal, allowed_root))

            # Mixed forward and backward slash paths
            mixed_slash = Path(f"{str(allowed_root).replace('\\', '/')}/Logs/app.log")
            self.assertTrue(is_safe_app_path(mixed_slash, allowed_root))

    def test_wf_sec_04_windows_semantics_and_drive_mismatches(self):
        """WF-SEC-04: is_safe_app_path must reject drive mismatches and handle case insensitivity on Windows."""
        root = Path(r"C:\WinFixAI\Data")
        diff_drive = Path(r"D:\WinFixAI\Data\winfix.db")

        # Cross-drive reference must be rejected
        self.assertFalse(is_safe_app_path(diff_drive, root))

        # Case variations of valid nested paths must be accepted on Windows
        cased_path = Path(r"c:\winfixai\data\sub\test.txt")
        self.assertTrue(is_safe_app_path(cased_path, root))

    def test_wf_sec_04_invalid_and_unsupported_inputs_fail_closed(self):
        """WF-SEC-04: is_safe_app_path must fail closed on None, empty strings, and UNC targets."""
        valid_root = Path(r"C:\WinFixAI\Data")

        invalid_targets = [
            None,
            "",
            "   ",
            Path(""),
            Path(r"\\192.168.1.1\share\WinFixAI\Data"),
            Path(r"//remote_server/data"),
        ]
        for bad_target in invalid_targets:
            with self.subTest(bad_target=str(bad_target)):
                self.assertFalse(is_safe_app_path(bad_target, valid_root))

        # Invalid root must fail closed
        self.assertFalse(is_safe_app_path(valid_root / "file.txt", None))
        self.assertFalse(is_safe_app_path(valid_root / "file.txt", Path("")))

    def test_wf_sec_04_initialize_app_directories_enforces_containment(self):
        """WF-SEC-04: initialize_app_directories must reject subdirectories escaping root_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            legit_root = base_dir / "WinFix_Legit"
            escaped_logs = base_dir / "WinFix_Legit_Sibling" / "Logs"

            forged_paths = AppPaths(
                root_dir=legit_root,
                data_dir=legit_root / "Data",
                logs_dir=escaped_logs,  # Sibling escape attempt!
                config_dir=legit_root / "Config",
                temp_dir=legit_root / "Temp",
                database_path=legit_root / "Data" / "winfix.db",
                schema_path=Path(__file__).resolve().parent.parent / "database" / "schema.sql",
            )

            results = initialize_app_directories(forged_paths)
            self.assertTrue(results["root"])
            self.assertTrue(results["data"])
            self.assertFalse(results["logs"], "Escaped logs directory must be blocked from creation")
            self.assertFalse(escaped_logs.exists(), "Escaped directory must not be created on disk")

    def test_wf_sec_05_requirements_pinned_strictly(self):
        """WF-SEC-05: All dependencies in requirements.txt must have explicit '==' version pins."""
        root_dir = Path(__file__).resolve().parent.parent
        req_file = root_dir / "requirements.txt"
        self.assertTrue(req_file.exists(), "requirements.txt must exist")

        lines = [
            line.strip()
            for line in req_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertGreater(len(lines), 0, "requirements.txt must not be empty")

        required_packages = {
            "streamlit",
            "ollama",
            "psutil",
            "pywin32",
            "faster-whisper",
            "av",
            "pyyaml",
            "pillow",
            "numpy",
        }
        declared_packages = set()

        for line in lines:
            with self.subTest(requirement_line=line):
                self.assertIn("==", line, f"Requirement '{line}' must be pinned with '=='")
                pkg_name, version = line.split("==", 1)
                pkg_normalized = pkg_name.strip().lower()
                declared_packages.add(pkg_normalized)
                self.assertTrue(version.strip(), f"Package '{pkg_name}' has an empty version")

        for req_pkg in required_packages:
            self.assertIn(req_pkg, declared_packages, f"Required direct runtime dependency '{req_pkg}' missing from requirements.txt")

    def test_wf_sec_05_reproducible_lockfile_exists_and_valid(self):
        """WF-SEC-05: requirements.lock must exist and contain complete pinned transitive closure."""
        root_dir = Path(__file__).resolve().parent.parent
        lock_file = root_dir / "requirements.lock"
        self.assertTrue(lock_file.exists(), "requirements.lock must exist")

        lock_lines = [
            line.strip()
            for line in lock_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertGreater(len(lock_lines), 20, "requirements.lock must contain transitive closure")

        for line in lock_lines:
            req_part = line.split(";")[0].strip()
            if req_part:
                with self.subTest(lock_entry=req_part):
                    self.assertIn("==", req_part, f"Lockfile entry '{req_part}' must be pinned with '=='")

    def test_wf_sec_05_package_dependency_consistency(self):
        """WF-SEC-05: Environment must have zero broken requirements or dependency conflicts."""
        import os
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"pip check reported broken requirements:\n{result.stdout}\n{result.stderr}")
        self.assertIn("no broken requirements found", result.stdout.lower())

    def test_wf_sec_06_negative_host_binding_rejection(self):
        """WF-SEC-06: Launchers must reject 0.0.0.0, LAN IPs, IPv6 wildcards, and external hosts."""
        import os
        import subprocess
        import sys

        root_dir = Path(__file__).resolve().parent.parent
        launchers = [
            root_dir / "winfix_launcher.py",
            root_dir / "build" / "dist" / "WinFixAI" / "winfix_launcher.py",
        ]
        unsafe_hosts = ["0.0.0.0", "::", "192.168.1.100", "10.0.0.1", "172.23.205.126", "evil.com"]

        for launcher in launchers:
            for bad_host in unsafe_hosts:
                with self.subTest(launcher=launcher.name, host=bad_host):
                    res = subprocess.run(
                        [sys.executable, "-B", str(launcher), "--host", bad_host],
                        capture_output=True,
                        text=True,
                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    )
                    self.assertEqual(res.returncode, 1, f"Expected returncode 1 for {bad_host}")
                    self.assertIn("CRITICAL SECURITY ERROR", res.stdout + res.stderr)
                    self.assertIn("strictly prohibited", res.stdout + res.stderr)

    def test_wf_sec_06_config_toml_and_batch_loopback_invariants(self):
        """WF-SEC-06: Config files and batch scripts must strictly enforce loopback binding."""
        root_dir = Path(__file__).resolve().parent.parent

        # 1. Source .streamlit/config.toml
        src_toml = (root_dir / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('address = "127.0.0.1"', src_toml)
        self.assertNotIn("0.0.0.0", src_toml)

        # 2. Packaged .streamlit/config.toml
        dist_toml = (root_dir / "build" / "dist" / "WinFixAI" / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('address = "127.0.0.1"', dist_toml)
        self.assertNotIn("0.0.0.0", dist_toml)

        # 3. launch_offline.bat
        batch_script = (root_dir / "launch_offline.bat").read_text(encoding="utf-8")
        self.assertIn("--host 127.0.0.1", batch_script)
        self.assertNotIn("--host 0.0.0.0", batch_script)

    def test_wf_sec_06_live_network_isolation_evidence(self):
        """WF-SEC-06: Validate empirical live socket listening and LAN blocking evidence."""
        root_dir = Path(__file__).resolve().parent.parent
        evidence_file = root_dir / "scratch" / "wf_sec_06_evidence.json"
        if not evidence_file.exists():
            self.skipTest("Live socket verification evidence artifact not present in scratch/")

        with open(evidence_file, "r", encoding="utf-8") as f:
            evidence = json.load(f)

        for launcher_key in ["source_launcher", "packaged_launcher"]:
            data = evidence.get(launcher_key, {})
            with self.subTest(launcher=launcher_key):
                self.assertTrue(data.get("is_loopback"))
                self.assertTrue(data.get("is_not_wildcard"))
                self.assertTrue(data.get("is_not_lan"))
                self.assertTrue(data.get("listening_address", "").startswith("127.0.0.1"))
                self.assertTrue(data.get("probe_127", {}).get("reachable"))
                self.assertTrue(data.get("probe_localhost", {}).get("reachable"))
                self.assertFalse(data.get("probe_lan", {}).get("reachable"))


if __name__ == "__main__":
    unittest.main()
