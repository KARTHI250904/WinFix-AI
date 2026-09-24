"""Repository for managing troubleshooting sessions in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class SessionRepository:
    """Handles CRUD operations for the `sessions` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def create(
        self,
        mode: str = "tutor",
        status: str = "active",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new troubleshooting session record."""
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()

        query = """
            INSERT INTO sessions (id, mode, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (sid, mode, status, now_str, now_str))

        logger.debug("Created session %s (mode=%s, status=%s)", sid, mode, status)
        return {
            "id": sid,
            "mode": mode,
            "status": status,
            "created_at": now_str,
            "updated_at": now_str,
        }

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a session by its unique ID."""
        query = "SELECT * FROM sessions WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update(
        self,
        session_id: str,
        status: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update session status or mode."""
        existing = self.get(session_id)
        if not existing:
            return None

        new_status = status if status is not None else existing["status"]
        new_mode = mode if mode is not None else existing["mode"]
        now_str = datetime.now().isoformat()

        query = """
            UPDATE sessions
            SET status = ?, mode = ?, updated_at = ?
            WHERE id = ?;
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (new_status, new_mode, now_str, session_id))

        return self.get(session_id)

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recently created sessions ordered by timestamp descending."""
        query = "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Count total sessions recorded."""
        query = "SELECT COUNT(*) AS total FROM sessions;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query)
            row = cursor.fetchone()
            return int(row["total"]) if row else 0

    def delete(self, session_id: str) -> bool:
        """Delete a session by ID (cascades to related records)."""
        query = "DELETE FROM sessions WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            return cursor.rowcount > 0
