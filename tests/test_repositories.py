"""Tests for WinFix AI SQLite repository interfaces and safety enforcement."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.db import DatabaseManager
from database.repositories import (
    DiagnosticRepository,
    FeedbackRepository,
    ProblemRepository,
    SessionRepository,
    SettingsRepository,
    SolutionRepository,
    ToolExecutionRepository,
)


class TestRepositories(unittest.TestCase):
    """Isolated test suite for all SQLite repository classes."""

    def setUp(self) -> None:
        """Create an isolated temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_repos.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db_manager.init_db()

        # Instantiate repositories with test DB
        self.session_repo = SessionRepository(self.db_manager)
        self.problem_repo = ProblemRepository(self.db_manager)
        self.diag_repo = DiagnosticRepository(self.db_manager)
        self.tool_repo = ToolExecutionRepository(self.db_manager)
        self.sol_repo = SolutionRepository(self.db_manager)
        self.fb_repo = FeedbackRepository(self.db_manager)
        self.settings_repo = SettingsRepository(self.db_manager)

    def tearDown(self) -> None:
        """Clean up temporary directory and database file."""
        self.temp_dir.cleanup()

    # --- SESSIONS ---
    def test_session_lifecycle(self) -> None:
        """Verify session creation, retrieval, updating, listing, and deletion."""
        session = self.session_repo.create(mode="tutor", status="active", session_id="test_s1")
        self.assertEqual(session["id"], "test_s1")
        self.assertEqual(session["mode"], "tutor")

        # Get
        fetched = self.session_repo.get("test_s1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], "test_s1")

        # Update
        updated = self.session_repo.update("test_s1", status="completed", mode="autopilot")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["mode"], "autopilot")

        # List
        self.session_repo.create(mode="autopilot", session_id="test_s2")
        sessions_list = self.session_repo.list_recent(limit=10)
        self.assertEqual(len(sessions_list), 2)
        self.assertEqual(self.session_repo.count(), 2)

        # Delete
        self.assertTrue(self.session_repo.delete("test_s1"))
        self.assertIsNone(self.session_repo.get("test_s1"))
        self.assertEqual(self.session_repo.count(), 1)

    # --- PROBLEMS ---
    def test_problem_lifecycle(self) -> None:
        """Verify problem creation, retrieval, update, and session relationship."""
        self.session_repo.create(session_id="sess_p1")
        prob = self.problem_repo.create(
            session_id="sess_p1",
            raw_input="Wi-Fi not connecting",
            input_type="text",
            category="network",
            confidence=0.92,
            problem_id="prob_01",
        )
        self.assertEqual(prob["id"], "prob_01")
        self.assertEqual(prob["category"], "network")

        # Get
        fetched = self.problem_repo.get("prob_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["raw_input"], "Wi-Fi not connecting")

        # Update category
        updated = self.problem_repo.update_category("prob_01", category="network_wifi", confidence=0.98)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["category"], "network_wifi")
        self.assertEqual(updated["confidence"], 0.98)

        # List for session
        self.problem_repo.create(session_id="sess_p1", raw_input="DNS issue", problem_id="prob_02")
        probs = self.problem_repo.list_for_session("sess_p1")
        self.assertEqual(len(probs), 2)

    # --- DIAGNOSTICS ---
    def test_diagnostics_lifecycle(self) -> None:
        """Verify diagnostic creation, retrieval, and listing for a session."""
        self.session_repo.create(session_id="sess_d1")
        diag = self.diag_repo.create(
            session_id="sess_d1",
            tool_name="check_dns",
            status="failed",
            evidence_json='{"dns_server": "192.168.1.1", "lookup": false}',
            diagnostic_id="diag_01",
        )
        self.assertEqual(diag["id"], "diag_01")

        # Get
        fetched = self.diag_repo.get("diag_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["tool_name"], "check_dns")
        self.assertEqual(fetched["status"], "failed")

        # List for session
        self.diag_repo.create(session_id="sess_d1", tool_name="ping_gateway", status="success")
        diags = self.diag_repo.list_for_session("sess_d1")
        self.assertEqual(len(diags), 2)

    # --- TOOL EXECUTIONS ---
    def test_tool_executions_lifecycle(self) -> None:
        """Verify tool execution audit logging and query methods."""
        self.session_repo.create(session_id="sess_t1")
        exec_record = self.tool_repo.create(
            session_id="sess_t1",
            tool_name="get_ip_configuration",
            risk_level="SAFE",
            requires_admin=False,
            success=True,
            duration_ms=45,
            result_json='{"ip": "192.168.1.50"}',
            execution_id="exec_01",
        )
        self.assertEqual(exec_record["id"], "exec_01")
        self.assertTrue(exec_record["success"])
        self.assertFalse(exec_record["requires_admin"])

        # Get
        fetched = self.tool_repo.get("exec_01")
        self.assertIsNotNone(fetched)
        self.assertIsInstance(fetched["success"], bool)
        self.assertTrue(fetched["success"])
        self.assertIsInstance(fetched["requires_admin"], bool)
        self.assertFalse(fetched["requires_admin"])

        # List for session
        self.tool_repo.create(
            session_id="sess_t1",
            tool_name="flush_dns",
            risk_level="MEDIUM",
            requires_admin=True,
            success=True,
            duration_ms=120,
        )
        history = self.tool_repo.list_for_session("sess_t1")
        self.assertEqual(len(history), 2)

    # --- SOLUTIONS ---
    def test_solutions_lifecycle(self) -> None:
        """Verify solution recording, verification status updates, and session listing."""
        self.session_repo.create(session_id="sess_sol1")
        sol = self.sol_repo.create(
            session_id="sess_sol1",
            proposed_repair="Flush DNS Cache",
            repair_executed=False,
            verified_status="unverified",
            solution_id="sol_01",
        )
        self.assertEqual(sol["id"], "sol_01")
        self.assertFalse(sol["repair_executed"])

        # Update
        updated = self.sol_repo.update(
            "sol_01",
            repair_executed=True,
            verified_status="fixed",
            verification_notes="DNS lookup passed after cache clear",
        )
        self.assertIsNotNone(updated)
        self.assertTrue(updated["repair_executed"])
        self.assertEqual(updated["verified_status"], "fixed")

        # List for session
        solutions = self.sol_repo.list_for_session("sess_sol1")
        self.assertEqual(len(solutions), 1)

    # --- FEEDBACK ---
    def test_feedback_lifecycle(self) -> None:
        """Verify feedback creation, retrieval, and session listing."""
        self.session_repo.create(session_id="sess_fb1")
        fb = self.fb_repo.create(
            session_id="sess_fb1",
            resolved=True,
            rating=5,
            comments="Very clear explanation!",
            feedback_id="fb_01",
        )
        self.assertEqual(fb["id"], "fb_01")
        self.assertTrue(fb["resolved"])

        # Get
        fetched = self.fb_repo.get("fb_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["rating"], 5)
        self.assertTrue(fetched["resolved"])

        # Get for session
        by_session = self.fb_repo.get_for_session("sess_fb1")
        self.assertIsNotNone(by_session)
        self.assertEqual(by_session["id"], "fb_01")

        # List all
        all_fb = self.fb_repo.list_all()
        self.assertEqual(len(all_fb), 1)

    # --- SETTINGS ---
    def test_settings_lifecycle(self) -> None:
        """Verify setting insertion, update (upsert), retrieval, listing, and deletion."""
        # Get nonexistent
        self.assertIsNone(self.settings_repo.get("theme"))
        self.assertEqual(self.settings_repo.get("theme", "dark"), "dark")

        # Set
        self.settings_repo.set("theme", "light")
        self.assertEqual(self.settings_repo.get("theme"), "light")

        # Update existing (upsert)
        self.settings_repo.set("theme", "system")
        self.assertEqual(self.settings_repo.get("theme"), "system")

        # Add another setting
        self.settings_repo.set("notifications_enabled", "true")
        all_settings = self.settings_repo.list_all()
        self.assertEqual(all_settings, {"notifications_enabled": "true", "theme": "system"})

        # Delete
        self.assertTrue(self.settings_repo.delete("theme"))
        self.assertIsNone(self.settings_repo.get("theme"))
        self.assertFalse(self.settings_repo.delete("nonexistent"))

    # --- DATABASE SAFETY & CONSTRAINTS ---
    def test_foreign_key_enforcement(self) -> None:
        """Verify inserting child records with non-existent session_id raises IntegrityError."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.problem_repo.create(
                session_id="non_existent_session_id",
                raw_input="Crash error",
            )

    def test_cascade_delete(self) -> None:
        """Verify deleting a parent session cascades and removes all linked child records."""
        self.session_repo.create(session_id="sess_cascade")
        self.problem_repo.create(session_id="sess_cascade", raw_input="Network problem")
        self.diag_repo.create(session_id="sess_cascade", tool_name="check_dns", status="failed")
        self.tool_repo.create(
            session_id="sess_cascade",
            tool_name="ping_gateway",
            risk_level="SAFE",
            requires_admin=False,
            success=True,
            duration_ms=10,
        )
        self.sol_repo.create(session_id="sess_cascade", proposed_repair="Reset DNS")
        self.fb_repo.create(session_id="sess_cascade", resolved=True)

        # Delete session
        self.assertTrue(self.session_repo.delete("sess_cascade"))

        # Verify child tables are empty
        self.assertEqual(len(self.problem_repo.list_for_session("sess_cascade")), 0)
        self.assertEqual(len(self.diag_repo.list_for_session("sess_cascade")), 0)
        self.assertEqual(len(self.tool_repo.list_for_session("sess_cascade")), 0)
        self.assertEqual(len(self.sol_repo.list_for_session("sess_cascade")), 0)
        self.assertIsNone(self.fb_repo.get_for_session("sess_cascade"))

    def test_parameterized_query_safety(self) -> None:
        """Verify malicious input containing SQL injection patterns is safely stored as literal text."""
        self.session_repo.create(session_id="sess_injection")
        malicious_input = "'); DROP TABLE sessions; --"
        prob = self.problem_repo.create(
            session_id="sess_injection",
            raw_input=malicious_input,
            category="'; DELETE FROM problems; --",
        )
        fetched = self.problem_repo.get(prob["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["raw_input"], malicious_input)
        # Verify sessions table still exists and is unaffected
        self.assertEqual(self.session_repo.count(), 1)


if __name__ == "__main__":
    unittest.main()
