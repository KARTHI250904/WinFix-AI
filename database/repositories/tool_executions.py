"""Repository for logging tool execution audits in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class ToolExecutionRepository:
    """Handles audit logging and queries for the `tool_executions` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def create(
        self,
        session_id: str,
        tool_name: str,
        risk_level: str,
        requires_admin: bool,
        success: bool,
        duration_ms: int,
        error_message: Optional[str] = None,
        result_json: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an explicit tool execution audit entry."""
        eid = execution_id or f"exec_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        admin_int = 1 if requires_admin else 0
        success_int = 1 if success else 0

        query = """
            INSERT INTO tool_executions (
                id, session_id, tool_name, risk_level, requires_admin,
                success, duration_ms, error_message, result_json, executed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    eid,
                    session_id,
                    tool_name,
                    risk_level,
                    admin_int,
                    success_int,
                    duration_ms,
                    error_message,
                    result_json,
                    now_str,
                ),
            )

        logger.debug("Logged tool execution %s (%s, success=%s)", eid, tool_name, success)
        return {
            "id": eid,
            "session_id": session_id,
            "tool_name": tool_name,
            "risk_level": risk_level,
            "requires_admin": requires_admin,
            "success": success,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "result_json": result_json,
            "executed_at": now_str,
        }

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific tool execution audit record."""
        query = "SELECT * FROM tool_executions WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["requires_admin"] = bool(res["requires_admin"])
            res["success"] = bool(res["success"])
            return res

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """List all tool executions recorded for a given session."""
        query = "SELECT * FROM tool_executions WHERE session_id = ? ORDER BY executed_at ASC;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["requires_admin"] = bool(item["requires_admin"])
                item["success"] = bool(item["success"])
                results.append(item)
            return results
