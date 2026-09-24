"""Repository for storing user feedback and resolution ratings in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class FeedbackRepository:
    """Handles CRUD operations for the `feedback` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def create(
        self,
        session_id: str,
        resolved: bool,
        rating: Optional[int] = None,
        comments: Optional[str] = None,
        feedback_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record user feedback for a troubleshooting session."""
        fid = feedback_id or f"fb_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        resolved_int = 1 if resolved else 0

        query = """
            INSERT INTO feedback (id, session_id, resolved, rating, comments, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (fid, session_id, resolved_int, rating, comments, now_str))

        logger.debug("Recorded feedback %s for session %s (resolved=%s)", fid, session_id, resolved)
        return {
            "id": fid,
            "session_id": session_id,
            "resolved": resolved,
            "rating": rating,
            "comments": comments,
            "created_at": now_str,
        }

    def get(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific feedback entry by ID."""
        query = "SELECT * FROM feedback WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (feedback_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["resolved"] = bool(res["resolved"])
            return res

    def get_for_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the latest feedback entry for a session."""
        query = "SELECT * FROM feedback WHERE session_id = ? ORDER BY created_at DESC LIMIT 1;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["resolved"] = bool(res["resolved"])
            return res

    def list_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List feedback records ordered by creation date descending."""
        query = "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (limit,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["resolved"] = bool(item["resolved"])
                results.append(item)
            return results
