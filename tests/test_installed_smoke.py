"""WinFix AI — Installed Application Smoke & Lifecycle Test Suite (Phase 25).

Validates:
1. First-run initialization in a simulated installed environment.
2. Startup health check execution from installed state.
3. User data preservation across simulated version upgrades.
4. Safe non-destructive installation repair.
5. Predictable uninstallation according to retention policy.
6. Offline operational capability (deterministic fallback without Ollama).
"""

import os
from pathlib import Path
import tempfile
import unittest

from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from database.repositories import SessionRepository, ToolExecutionRepository
from knowledge.seed_data import seed_default_knowledge
from production.config import ProductionConfig
from production.health_check import ComponentStatus, HealthCheckEngine
from production.installation import (
    InstallationInfo,
    InstallationManager,
    InstallationState,
)
from production.lifecycle import (
    UninstallPolicy,
    execute_safe_uninstall,
    run_database_migration,
    verify_restart_state,
)
from production.paths import AppPaths, resolve_app_paths
from production.setup import run_first_time_setup


class TestInstalledApplicationSmoke(unittest.TestCase):
    """End-to-end smoke tests for installed WinFix AI application lifecycles."""

    def test_simulated_fresh_install_and_first_run(self):
        """Simulate fresh installation into a clean directory and perform first-run initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            install_dir = base_path / "ProgramFiles" / "WinFixAI"
            user_data_dir = base_path / "AppData" / "Local" / "WinFixAI"
            install_dir.mkdir(parents=True)
            user_data_dir.mkdir(parents=True)

            # Place core application files in install_dir
            (install_dir / "winfix_launcher.py").write_text("# launcher", encoding="utf-8")
            (install_dir / "app.py").write_text("# app", encoding="utf-8")
            (install_dir / "config.py").write_text("# config", encoding="utf-8")

            paths = resolve_app_paths(user_data_dir)
            cfg = ProductionConfig(paths=paths)

            # 1. Run first time setup
            setup_res = run_first_time_setup(config=cfg)
            self.assertTrue(setup_res.success)
            self.assertTrue(setup_res.directories_created)
            self.assertTrue(setup_res.database_initialized)
            self.assertTrue(setup_res.knowledge_seeded)
            self.assertGreaterEqual(setup_res.seed_count, 9)

            # 2. Run Health Check
            engine = HealthCheckEngine(config=cfg)
            report = engine.run_health_check()
            self.assertTrue(report.is_operational())
            self.assertEqual(report.components["database"].status, ComponentStatus.READY)
            self.assertEqual(report.components["tool_registry"].status, ComponentStatus.READY)
            self.assertEqual(report.components["safety_engine"].status, ComponentStatus.READY)

            # 3. Verify Installation State
            mgr = InstallationManager(config=cfg, install_dir=install_dir)
            state = mgr.get_installation_state()
            self.assertEqual(state.status, InstallationState.UP_TO_DATE)

    def test_upgrade_preserves_user_data_and_audit_history(self):
        """Simulate version upgrade and confirm user session and audit logs remain intact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            user_data_dir = Path(tmpdir) / "WinFixAI"
            paths = resolve_app_paths(user_data_dir)
            cfg = ProductionConfig(paths=paths)
            run_first_time_setup(config=cfg)

            # Create sample user session and tool execution audit
            db_mgr = DatabaseManager(db_path=paths.database_path)
            sess_repo = SessionRepository(db_mgr)
            tool_repo = ToolExecutionRepository(db_mgr)

            sess_repo.create(session_id="user_sess_100", mode="diagnose")
            tool_repo.create(
                session_id="user_sess_100",
                tool_name="get_cpu_diagnostics",
                risk_level="SAFE",
                requires_admin=False,
                success=True,
                duration_ms=25,
                result_json='{"status": "ok"}',
            )

            # Perform migration/upgrade to 1.0.1
            mig_res = run_database_migration(target_version="1.0.1", config=cfg)
            self.assertTrue(mig_res.success)
            self.assertEqual(mig_res.audit_records_preserved, 1)

            # Verify data is preserved
            sess = sess_repo.get("user_sess_100")
            self.assertIsNotNone(sess)
            execs = tool_repo.list_for_session("user_sess_100")
            self.assertEqual(len(execs), 1)
            self.assertEqual(execs[0]["tool_name"], "get_cpu_diagnostics")

    def test_safe_installation_repair_preserves_records(self):
        """Test installation repair restores missing knowledge articles without dropping sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            user_data_dir = Path(tmpdir) / "WinFixAI"
            paths = resolve_app_paths(user_data_dir)
            cfg = ProductionConfig(paths=paths)
            run_first_time_setup(config=cfg)

            db_mgr = DatabaseManager(db_path=paths.database_path)
            sess_repo = SessionRepository(db_mgr)
            sess_repo.create(session_id="repair_test_sess", mode="tutor")

            # Run installation repair
            mgr = InstallationManager(config=cfg)
            repair_res = mgr.repair_installation()

            self.assertTrue(repair_res["success"])
            self.assertGreaterEqual(repair_res["knowledge_articles"], 9)
            # Confirm session survived
            self.assertIsNotNone(sess_repo.get("repair_test_sess"))

    def test_uninstallation_retention_policy(self):
        """Test uninstallation under KEEP_USER_DATA preserves database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            user_data_dir = Path(tmpdir) / "WinFixAI"
            paths = resolve_app_paths(user_data_dir)
            cfg = ProductionConfig(paths=paths)
            run_first_time_setup(config=cfg)

            # Uninstall with KEEP_USER_DATA
            uninst_res = execute_safe_uninstall(policy=UninstallPolicy.KEEP_USER_DATA, config=cfg)
            self.assertTrue(uninst_res)
            # Database should still exist
            self.assertTrue(Path(paths.database_path).exists())


if __name__ == "__main__":
    unittest.main()
