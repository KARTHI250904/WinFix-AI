"""WinFix AI — Package Content & Artifact Validation Suite (Phase 25).

Validates:
1. Production distribution package contents against allowlist.
2. Absence of development-only files (.git, .venv, .pytest_cache, tests).
3. Absence of secrets, credentials, or development environment files (.env).
4. BUILD_MANIFEST.json structural and cryptographic consistency.
5. SHA256SUMS.txt format and accuracy.
"""

import json
from pathlib import Path
import unittest

from build.build_windows import (
    PRODUCTION_DIRECTORIES,
    PRODUCTION_FILES,
    build_package,
    compute_sha256,
)
from production.version import APP_NAME, APP_VERSION


class TestPackageContents(unittest.TestCase):
    """Test suite validating production distribution package completeness and cleanliness."""

    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.build_dir = cls.root_dir / "build"
        cls.dist_dir = cls.build_dir / "dist" / "WinFixAI"
        cls.manifest_file = cls.build_dir / "BUILD_MANIFEST.json"

        # Ensure package is built
        if not cls.dist_dir.exists() or not cls.manifest_file.exists():
            success, _ = build_package()
            assert success, "Failed to build package for testing"

    def test_required_production_files_present_in_package(self):
        """All top-level production files must exist in the distribution package."""
        for filename in PRODUCTION_FILES:
            with self.subTest(file=filename):
                target = self.dist_dir / filename
                self.assertTrue(target.exists(), f"Required file '{filename}' missing from package!")

    def test_required_production_directories_present_in_package(self):
        """All production modules must be present in the distribution package."""
        for dirname in PRODUCTION_DIRECTORIES:
            with self.subTest(directory=dirname):
                target = self.dist_dir / dirname
                self.assertTrue(target.exists() and target.is_dir(), f"Required directory '{dirname}' missing from package!")

    def test_development_artifacts_excluded_from_package(self):
        """Package must NOT contain development-only or temporary files."""
        forbidden_substrings = [
            ".git",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            "tests",
            ".env",
            "scratch",
        ]

        found_forbidden = []
        for file_path in self.dist_dir.rglob("*"):
            rel_path = file_path.relative_to(self.dist_dir).as_posix().lower()
            for forbidden in forbidden_substrings:
                if forbidden in rel_path.split("/"):
                    found_forbidden.append(rel_path)

        self.assertEqual(len(found_forbidden), 0, f"Development artifacts detected in package:\n{found_forbidden}")

    def test_build_manifest_structure_and_integrity(self):
        """Validate BUILD_MANIFEST.json metadata schema and values."""
        self.assertTrue(self.manifest_file.exists())
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("application_name"), APP_NAME)
        self.assertEqual(manifest.get("version"), APP_VERSION)
        self.assertEqual(manifest.get("platform"), "windows")
        self.assertGreater(manifest.get("file_count", 0), 50)
        self.assertIn("checksums", manifest)

        # Verify a sample of checksums from manifest
        checksums = manifest["checksums"]
        for rel_path, expected_hash in list(checksums.items())[:10]:
            actual_file = self.dist_dir / rel_path
            self.assertTrue(actual_file.exists())
            self.assertEqual(compute_sha256(actual_file), expected_hash)

    def test_sha256sums_file_validity(self):
        """Validate SHA256SUMS.txt exists and matches package files."""
        sums_file = self.build_dir / "artifacts" / "SHA256SUMS.txt"
        self.assertTrue(sums_file.exists())

        lines = sums_file.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 50)
        for line in lines[:10]:
            parts = line.strip().split("  ")
            self.assertEqual(len(parts), 2)
            digest, filename = parts[0], parts[1]
            target = self.dist_dir / filename
            self.assertTrue(target.exists())
            self.assertEqual(compute_sha256(target), digest)


if __name__ == "__main__":
    unittest.main()
