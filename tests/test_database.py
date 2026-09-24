"""Tests for WinFix AI SQLite database initialization and management."""

from pathlib import Path
import tempfile
import unittest

from database.db import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    """Test suite for DatabaseManager."""

    def setUp(self) -> None:
        """Create a temporary directory and database file for isolated testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_winfix.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_database_initialization(self) -> None:
        """Verify that init_db creates all required Phase 0 schema tables."""
        res = self.db_manager.init_db()
        self.assertTrue(res["success"], f"Database init failed: {res.get('error')}")
        self.assertTrue(self.db_path.exists())

        expected_tables = {
            "sessions",
            "problems",
            "diagnostics",
            "tool_executions",
            "solutions",
            "feedback",
            "settings",
        }
        actual_tables = set(self.db_manager.get_existing_tables())
        self.assertTrue(
            expected_tables.issubset(actual_tables),
            f"Expected tables {expected_tables} missing from {actual_tables}",
        )

    def test_database_health_check(self) -> None:
        """Verify health check returns valid connectivity and table counts."""
        # Uninitialized health
        health_before = self.db_manager.check_health()
        self.assertTrue(health_before["connected"])
        self.assertEqual(health_before["tables_count"], 0)

        # After init
        self.db_manager.init_db()
        health_after = self.db_manager.check_health()
        self.assertTrue(health_after["connected"])
        self.assertGreaterEqual(health_after["tables_count"], 7)

    def test_parameterized_query_execution(self) -> None:
        """Verify parameterized queries and foreign key constraints work as expected."""
        self.db_manager.init_db()
        with self.db_manager.get_connection() as conn:
            # Insert session
            conn.execute(
                "INSERT INTO sessions (id, mode, status) VALUES (?, ?, ?);",
                ("sess_001", "tutor", "active"),
            )
            # Insert problem
            conn.execute(
                "INSERT INTO problems (id, session_id, raw_input, category) VALUES (?, ?, ?, ?);",
                ("prob_001", "sess_001", "Internet disconnected", "network"),
            )

        with self.db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM problems WHERE id = ?;", ("prob_001",))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["session_id"], "sess_001")
            self.assertEqual(row["raw_input"], "Internet disconnected")
            self.assertEqual(row["category"], "network")


if __name__ == "__main__":
    unittest.main()
