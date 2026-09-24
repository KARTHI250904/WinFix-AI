"""Repository for managing application key-value configuration in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, Optional

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class SettingsRepository:
    """Handles CRUD operations for the `settings` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a string configuration value by key."""
        query = "SELECT value FROM settings WHERE key = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set(self, key: str, value: str) -> Dict[str, Any]:
        """Store or update a configuration key-value pair."""
        now_str = datetime.now().isoformat()
        query = """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at;
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (key, str(value), now_str))

        logger.debug("Persisted setting %s=%s", key, value)
        return {
            "key": key,
            "value": str(value),
            "updated_at": now_str,
        }

    def delete(self, key: str) -> bool:
        """Remove a configuration key from the settings table."""
        query = "DELETE FROM settings WHERE key = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (key,))
            return cursor.rowcount > 0

    def list_all(self) -> Dict[str, str]:
        """Retrieve all configuration settings as a dictionary."""
        query = "SELECT key, value FROM settings ORDER BY key ASC;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query)
            return {row["key"]: row["value"] for row in cursor.fetchall()}
