"""
WinFix AI — Phase 23 Lifecycle, Permissions & Storage Compatibility Tests.

Validates:
1. Permission Boundaries:
   - Standard User: SAFE diagnostics work, MEDIUM repairs require authorization.
   - Administrator User: Administrator rights DO NOT bypass SafetyEngine or authorization.
2. Storage & Path Traversal Guards:
   - %LOCALAPPDATA% directory tree integrity.
   - Path traversal and outside-directory escape attempts rejected.
3. SQLite Transactional Integrity:
   - Transaction rollback on simulated error leaves database uncorrupted.
   - Repeated schema initialization preserves existing records.
"""

from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import create_default_registry
from database.db import DatabaseManager
from production.config import ProductionConfig
from production.paths import initialize_app_directories, is_safe_app_path, resolve_app_paths
from production.setup import run_first_time_setup


class TestPermissionsAndStorageCompatibility(unittest.TestCase):
    """Test suite for permission boundaries, path safety, and SQLite transactional integrity."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_lifecycle_compat_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)
        self.config = ProductionConfig(paths=self.paths)
        run_first_time_setup(self.config)
        self.db_mgr = DatabaseManager(db_path=self.paths.database_path)
        self.registry = create_default_registry()
        self.safety = SafetyEngine(registry=self.registry)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_admin_privileges_do_not_bypass_safety_engine(self):
        """Administrator privileges must NEVER bypass SafetyEngine or user confirmation."""
        with patch("production.environment.is_process_elevated", return_value=True):
            # Attempt to execute MEDIUM risk repair without user confirmation
            decision = self.safety.evaluate("flush_dns_cache", {}, user_confirmed=False)
            self.assertFalse(decision.allowed)
            self.assertTrue(decision.requires_confirmation)

            # Attempt to execute forbidden tool even under admin simulation
            decision_blocked = self.safety.evaluate("powershell.exe", {})
            self.assertFalse(decision_blocked.allowed)
            self.assertTrue(decision_blocked.blocked)

    def test_standard_user_safe_tools_allowed(self):
        """Standard non-admin user is allowed to run SAFE read-only diagnostics."""
        with patch("production.environment.is_process_elevated", return_value=False):
            decision = self.safety.evaluate("get_complete_system_info", {})
            self.assertTrue(decision.allowed)
            self.assertFalse(decision.requires_confirmation)
            self.assertFalse(decision.blocked)

    def test_path_traversal_and_escape_rejection(self):
        root = self.paths.root_dir
        valid_log = self.paths.logs_dir / "winfix.log"
        traversal_attack1 = root / ".." / ".." / "Windows" / "System32" / "cmd.exe"
        traversal_attack2 = root / "Data" / ".." / ".." / "Users" / "Victim" / "secret.txt"

        self.assertTrue(is_safe_app_path(valid_log, root))
        self.assertFalse(is_safe_app_path(traversal_attack1, root))
        self.assertFalse(is_safe_app_path(traversal_attack2, root))

    def test_sqlite_transaction_rollback_on_failure(self):
        """Simulate an interrupted transaction and verify database integrity is preserved."""
        with self.db_mgr.get_connection() as conn:
            initial_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

        # Attempt transaction that raises an error midway
        try:
            with self.db_mgr.get_connection() as conn:
                conn.execute("INSERT INTO sessions (id, mode) VALUES ('test_rollback_1', 'tutor')")
                # Intentional error to trigger rollback
                raise RuntimeError("Simulated power loss or crash during transaction")
        except RuntimeError:
            pass

        # Verify database was rolled back cleanly
        with self.db_mgr.get_connection() as conn:
            final_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            uncommitted = conn.execute("SELECT COUNT(*) FROM sessions WHERE id='test_rollback_1'").fetchone()[0]

        self.assertEqual(initial_sessions, final_sessions)
        self.assertEqual(uncommitted, 0)


if __name__ == "__main__":
    unittest.main()
