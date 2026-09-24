"""Database connection and initialization module for WinFix AI.

Provides SQLite connection management, schema initialization, and
parameterized query execution in compliance with project safety rules.
"""

from contextlib import contextmanager
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, Optional

from config import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connections and baseline schema initialization."""

    def __init__(self, db_path: Optional[Path] = None, schema_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else config.database_path
        self.schema_path = Path(schema_path) if schema_path else config.schema_path

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding a SQLite connection with row factories and foreign keys enabled."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("Database transaction failed: %s", exc)
            raise
        finally:
            conn.close()

    def init_db(self) -> Dict[str, Any]:
        """Initialize SQLite database with the baseline schema.sql script."""
        try:
            if not self.schema_path.exists():
                err_msg = f"Schema file not found at {self.schema_path}"
                logger.error(err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "tables": []
                }

            schema_sql = self.schema_path.read_text(encoding="utf-8")
            with self.get_connection() as conn:
                conn.executescript(schema_sql)

            tables = self.get_existing_tables()
            logger.info("Database initialized successfully at %s with tables: %s", self.db_path, tables)
            return {
                "success": True,
                "db_path": str(self.db_path),
                "tables": tables,
                "error": None
            }
        except Exception as exc:
            logger.error("Failed to initialize database: %s", exc)
            return {
                "success": False,
                "db_path": str(self.db_path),
                "tables": [],
                "error": str(exc)
            }

    def get_existing_tables(self) -> list[str]:
        """Fetch list of user-created tables in the SQLite database."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            return [row["name"] for row in cursor.fetchall()]

    def check_health(self) -> Dict[str, Any]:
        """Verify database connectivity and return structured health status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT 1 AS alive;")
                result = cursor.fetchone()
                alive = result is not None and result["alive"] == 1
                tables = self.get_existing_tables()
                return {
                    "connected": alive,
                    "db_path": str(self.db_path),
                    "tables_count": len(tables),
                    "tables": tables,
                    "error": None
                }
        except Exception as exc:
            return {
                "connected": False,
                "db_path": str(self.db_path),
                "tables_count": 0,
                "tables": [],
                "error": str(exc)
            }


# Default shared database instance
db_manager = DatabaseManager()


def init_db(db_path: Optional[Path] = None, schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience functional interface to initialize the database."""
    manager = DatabaseManager(db_path=db_path, schema_path=schema_path) if (db_path or schema_path) else db_manager
    return manager.init_db()
