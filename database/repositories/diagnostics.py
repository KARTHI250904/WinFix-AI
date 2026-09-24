"""Repository for managing diagnostic results and evidence in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class DiagnosticRepository:
    """Handles CRUD operations for the `diagnostics` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def create(
        self,
        session_id: str,
        tool_name: str,
        status: str,
        evidence_json: Optional[str] = None,
        diagnostic_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a diagnostic inspection result for a session."""
        did = diagnostic_id or f"diag_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()

        query = """
            INSERT INTO diagnostics (id, session_id, tool_name, status, evidence_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (did, session_id, tool_name, status, evidence_json, now_str))

        logger.debug("Recorded diagnostic %s (%s: %s) for session %s", did, tool_name, status, session_id)
        return {
            "id": did,
            "session_id": session_id,
            "tool_name": tool_name,
            "status": status,
            "evidence_json": evidence_json,
            "created_at": now_str,
        }

    def get(self, diagnostic_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single diagnostic record by ID."""
        query = "SELECT * FROM diagnostics WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (diagnostic_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """List all diagnostic results recorded for a session."""
        query = "SELECT * FROM diagnostics WHERE session_id = ? ORDER BY created_at ASC;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            return [dict(row) for row in cursor.fetchall()]
