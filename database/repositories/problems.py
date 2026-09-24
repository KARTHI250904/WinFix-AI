"""Repository for managing identified user problems in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class ProblemRepository:
    """Handles CRUD operations for the `problems` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def create(
        self,
        session_id: str,
        raw_input: str,
        input_type: str = "text",
        category: Optional[str] = None,
        confidence: Optional[float] = None,
        problem_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new problem record associated with a session."""
        pid = problem_id or f"prob_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()

        query = """
            INSERT INTO problems (id, session_id, raw_input, input_type, category, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (pid, session_id, raw_input, input_type, category, confidence, now_str))

        logger.debug("Created problem %s for session %s", pid, session_id)
        return {
            "id": pid,
            "session_id": session_id,
            "raw_input": raw_input,
            "input_type": input_type,
            "category": category,
            "confidence": confidence,
            "created_at": now_str,
        }

    def get(self, problem_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a problem by ID."""
        query = "SELECT * FROM problems WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (problem_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """List all problems recorded for a given session."""
        query = "SELECT * FROM problems WHERE session_id = ? ORDER BY created_at ASC;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_category(
        self,
        problem_id: str,
        category: str,
        confidence: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update problem categorization and confidence score."""
        query = """
            UPDATE problems
            SET category = ?, confidence = ?
            WHERE id = ?;
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (category, confidence, problem_id))

        return self.get(problem_id)
