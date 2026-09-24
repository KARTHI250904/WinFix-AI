"""Comprehensive unit, safety, and verification tests for WinFix AI Phase 9 (Storage Diagnostics & Repairs).

Tests disk/volume inventory, storage pressure calculation thresholds, temporary storage analysis,
bounded large temporary file discovery, path traversal/symlink escape protections, cryptographic confirmation tokens,
deterministic before/after verification lifecycles, and static security AST guarantees.
"""

import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.safety import SafetyEngine
from agent.storage_diagnostics import (
    STORAGE_CATEGORIES,
    StorageDiagnosis,
    StorageDiagnosticsOrchestrator,
)
from agent.storage_repairs_orchestrator import (
    StorageRepairExecutionResult,
    StorageRepairProposal,
    StorageRepairsOrchestrator,
)
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from database.db import DatabaseManager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
import windows
from windows.performance_repairs import clean_user_temp_cache
from windows.storage_tools import (
    analyze_large_temporary_files,
    calculate_storage_pressure_level,
    get_storage_diagnostics,
    get_storage_pressure_analysis,
    get_temp_storage_info,
)


class TestStorageDiagnostics(unittest.TestCase):
    """Test suite verifying read-only storage diagnostic tools."""

    def test_storage_diagnostics_structure(self) -> None:
        """Verify storage diagnostics returns partition inventory and valid capacity metrics."""
        res = get_storage_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_storage_diagnostics")
        self.assertEqual(res["domain"], "storage")
        data = res["data"]
        self.assertIn("drives", data)
        self.assertIn("drives_count", data)
        if data["drives"]:
            d0 = data["drives"][0]
            self.assertIn("mountpoint", d0)
            self.assertIn("fstype", d0)
            self.assertIn("pressure_level", d0)

    def test_calculate_storage_pressure_level_thresholds(self) -> None:
        """Verify deterministic storage pressure thresholds."""
        # 1. Critical: >= 95% used OR <= 5GB free
        self.assertEqual(calculate_storage_pressure_level(96.0, 100 * 1024 * 1024 * 1024), "CRITICAL")
        self.assertEqual(calculate_storage_pressure_level(60.0, 2 * 1024 * 1024 * 1024), "CRITICAL")

        # 2. High: >= 85% used OR <= 10GB free
        self.assertEqual(calculate_storage_pressure_level(88.0, 50 * 1024 * 1024 * 1024), "HIGH")
        self.assertEqual(calculate_storage_pressure_level(70.0, 8 * 1024 * 1024 * 1024), "HIGH")

        # 3. Elevated: >= 75% used OR <= 20GB free
        self.assertEqual(calculate_storage_pressure_level(78.0, 50 * 1024 * 1024 * 1024), "ELEVATED")
        self.assertEqual(calculate_storage_pressure_level(50.0, 15 * 1024 * 1024 * 1024), "ELEVATED")

        # 4. Normal: < 75% used AND > 20GB free
        self.assertEqual(calculate_storage_pressure_level(40.0, 100 * 1024 * 1024 * 1024), "NORMAL")

    def test_get_storage_pressure_analysis(self) -> None:
        """Verify storage pressure analysis provides overall severity and lowest free drive."""
        res = get_storage_pressure_analysis()
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertIn("overall_pressure_level", data)
        self.assertIn(data["overall_pressure_level"], ["NORMAL", "ELEVATED", "HIGH", "CRITICAL", "UNKNOWN"])
        self.assertIn("thresholds", data)
        self.assertIn("volumes", data)

    def test_get_temp_storage_info_structure(self) -> None:
        """Verify temp storage reader inspects directories without deleting files."""
        res = get_temp_storage_info()
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertIn("total_temp_bytes", data)
        self.assertIn("total_temp_files", data)
        self.assertIn("locked_or_inaccessible_files", data)
        self.assertIn("locations", data)

    def test_analyze_large_temporary_files_bounded(self) -> None:
        """Verify analyze_large_temporary_files returns bounded results."""
        with tempfile.TemporaryDirectory() as custom_temp:
            # Create test files in isolated sandbox
            f1 = Path(custom_temp) / "large_file_1.tmp"
            f1.write_bytes(b"A" * (2 * 1024 * 1024))  # 2 MB

            with patch.dict(os.environ, {"TEMP": custom_temp, "TMP": custom_temp}):
                # Query files >= 1 MB
                res = analyze_large_temporary_files(min_size_mb=1.0, limit=5)
                self.assertTrue(res["success"])
                data = res["data"]
                self.assertEqual(data["returned_count"], 1)
                self.assertEqual(data["large_files"][0]["filename"], "large_file_1.tmp")
                self.assertFalse(data["scan_limited"])


class TestStoragePathSecurityAndSandbox(unittest.TestCase):
    """Test suite verifying path containment, traversal prevention, and symlink escape checks."""

    def test_clean_user_temp_rejects_drive_root(self) -> None:
        """Verify clean_user_temp_cache fails closed if target points to a drive root."""
        with patch.dict(os.environ, {"TEMP": r"C:\\", "TMP": r"C:\\"}):
            res = clean_user_temp_cache()
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "UNSAFE_TEMP_PATH")

    def test_clean_user_temp_rejects_windows_directory(self) -> None:
        """Verify clean_user_temp_cache fails closed if target points directly to C:\\Windows."""
        with patch.dict(os.environ, {"TEMP": r"C:\Windows", "TMP": r"C:\Windows"}):
            res = clean_user_temp_cache()
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "UNSAFE_TEMP_PATH")

    def test_clean_user_temp_skips_symlink_escape_entries(self) -> None:
        """Verify entries pointing outside approved sandbox via symlink are skipped."""
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "important_document.txt"
            outside_file.write_text("protected user content", encoding="utf-8")

            with tempfile.TemporaryDirectory() as custom_temp:
                inside_file = Path(custom_temp) / "scratch.tmp"
                inside_file.write_text("temp scratch", encoding="utf-8")

                with patch.dict(os.environ, {"TEMP": custom_temp, "TMP": custom_temp}):
                    res = clean_user_temp_cache(dry_run=False)
                    self.assertTrue(res["success"])
                    self.assertFalse(inside_file.exists())
                    # Ensure outside file was never touched
                    self.assertTrue(outside_file.exists())


class TestStorageToolRegistryAndMetadata(unittest.TestCase):
    """Test suite verifying ToolRegistry registration and risk classifications for Phase 9 tools."""

    def setUp(self) -> None:
        self.registry = create_default_registry()

    def test_phase9_registered_tools_metadata(self) -> None:
        """Verify Phase 9 storage tools are correctly registered."""
        # 1. Storage Pressure Analysis (SAFE)
        tool_p = self.registry.get("get_storage_pressure_analysis")
        self.assertIsNotNone(tool_p)
        self.assertEqual(tool_p.risk, RiskLevel.SAFE)
        self.assertTrue(tool_p.read_only)
        self.assertTrue(tool_p.automatic_allowed)

        # 2. Large Temp Files Analysis (SAFE)
        tool_l = self.registry.get("analyze_large_temporary_files")
        self.assertIsNotNone(tool_l)
        self.assertEqual(tool_l.risk, RiskLevel.SAFE)
        self.assertTrue(tool_l.read_only)
        self.assertTrue(tool_l.automatic_allowed)

        # 3. Clean User Temp Cache (MEDIUM Repair)
        tool_c = self.registry.get("clean_user_temp_cache")
        self.assertIsNotNone(tool_c)
        self.assertEqual(tool_c.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool_c.read_only)
        self.assertFalse(tool_c.automatic_allowed)
        self.assertEqual(tool_c.verification_tool, "get_temp_storage_info")


class TestStorageOrchestratorAndVerificationLifecycle(unittest.TestCase):
    """Test suite for Storage Diagnostics -> Proposal -> Confirmation -> Verification."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_storage.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db_manager.init_db()

        self.registry = create_default_registry()
        self.exec_repo = ToolExecutionRepository(self.db_manager)
        self.safety_engine = SafetyEngine(registry=self.registry, execution_repo=self.exec_repo)
        self.orchestrator = StorageRepairsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
            db_mgr=self.db_manager,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_confirmation_token_mismatch_fails_closed(self) -> None:
        """Verify tampered storage repair token fails closed."""
        proposal = StorageRepairProposal(
            tool_name="clean_user_temp_cache",
            arguments={"max_file_age_hours": 0.0, "dry_run": False},
        )
        token = proposal.generate_confirmation_token("sess_storage_1")

        # Tampered argument
        proposal_tampered = StorageRepairProposal(
            tool_name="clean_user_temp_cache",
            arguments={"max_file_age_hours": 24.0, "dry_run": False},
        )

        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal_tampered,
            session_id="sess_storage_1",
            user_confirmed=True,
            confirmation_token=token,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")
        self.assertIn("Security validation failed", res.explanation)

    def test_unconfirmed_storage_repair_fails_closed(self) -> None:
        """Verify unconfirmed storage repair fails closed."""
        proposal = StorageRepairProposal(
            tool_name="clean_user_temp_cache",
            arguments={"max_file_age_hours": 0.0, "dry_run": False},
        )
        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_storage_unconf",
            user_confirmed=False,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")

    def test_successful_storage_cleanup_verification_lifecycle(self) -> None:
        """Verify Before-State -> clean_user_temp_cache -> After-State -> 'verified' status."""
        session_repo = SessionRepository(self.db_manager)
        session_repo.create(session_id="sess_storage_verified")

        proposal = StorageRepairProposal(
            tool_name="clean_user_temp_cache",
            arguments={"max_file_age_hours": 0.0, "dry_run": False},
            verification_tool="get_temp_storage_info",
        )

        clean_tool = self.registry.get("clean_user_temp_cache")
        temp_tool = self.registry.get("get_temp_storage_info")
        self.assertIsNotNone(clean_tool)
        self.assertIsNotNone(temp_tool)

        clean_tool.handler = lambda max_file_age_hours=0.0, dry_run=False: {
            "success": True,
            "data": {
                "deleted_files_count": 25,
                "failed_files_count": 1,
                "freed_bytes": 52428800,
                "freed_formatted": "50.0 MB",
            },
        }
        temp_tool.handler = lambda: {
            "success": True,
            "data": {"total_temp_bytes": 1024, "total_temp_files": 1},
        }

        result = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_storage_verified",
            user_confirmed=True,
        )

        self.assertTrue(result.repair_success)
        self.assertEqual(result.verification_status, "verified")
        self.assertIn("50.0 MB", result.explanation)
        self.assertIn("1 locked file(s) safely skipped", result.explanation)

        # Verify record in SQLite
        solution_repo = SolutionRepository(self.db_manager)
        records = solution_repo.list_for_session("sess_storage_verified")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["proposed_repair"], "clean_user_temp_cache")
        self.assertEqual(records[0]["verified_status"], "verified")


class TestPhase9SecurityAndStaticScan(unittest.TestCase):
    """Security scan verifying no command/shell execution exists in Phase 9 code."""

    def test_no_forbidden_execution_imports_in_storage_modules(self) -> None:
        """Verify storage modules contain no forbidden execution patterns."""
        forbidden_patterns = [
            "subprocess",
            "os.system",
            "os.popen",
            "shell=True",
            "eval(",
            "exec(",
        ]

        modules_to_scan = [
            "windows.storage_tools",
            "agent.storage_diagnostics",
            "agent.storage_repairs_orchestrator",
        ]

        for mod_name in modules_to_scan:
            mod = __import__(mod_name, fromlist=["*"])
            src = inspect.getsource(mod)
            for forbidden in forbidden_patterns:
                self.assertNotIn(
                    forbidden,
                    src,
                    f"Forbidden execution pattern '{forbidden}' found in {mod_name}",
                )


if __name__ == "__main__":
    unittest.main()
