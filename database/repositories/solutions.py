"""Repository for tracking proposed solutions and verification outcomes in SQLite."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from database.db import DatabaseManager, db_manager

logger = logging.getLogger(__name__)


class SolutionRepository:
    """Handles CRUD operations for the `solutions` table."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager

    def create(
        self,
        session_id: str,
        proposed_repair: Optional[str] = None,
        repair_executed: bool = False,
        verified_status: str = "unverified",
        verification_notes: Optional[str] = None,
        solution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a proposed solution and initial verification state."""
        sol_id = solution_id or f"sol_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        exec_int = 1 if repair_executed else 0

        query = """
            INSERT INTO solutions (
                id, session_id, proposed_repair, repair_executed,
                verified_status, verification_notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    sol_id,
                    session_id,
                    proposed_repair,
                    exec_int,
                    verified_status,
                    verification_notes,
                    now_str,
                ),
            )

        logger.debug("Recorded solution %s for session %s (status=%s)", sol_id, session_id, verified_status)
        return {
            "id": sol_id,
            "session_id": session_id,
            "proposed_repair": proposed_repair,
            "repair_executed": repair_executed,
            "verified_status": verified_status,
            "verification_notes": verification_notes,
            "created_at": now_str,
        }

    def get(self, solution_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific solution by ID."""
        query = "SELECT * FROM solutions WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (solution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["repair_executed"] = bool(res["repair_executed"])
            return res

    def update(
        self,
        solution_id: str,
        repair_executed: Optional[bool] = None,
        verified_status: Optional[str] = None,
        verification_notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update execution state and verification outcome for a solution."""
        existing = self.get(solution_id)
        if not existing:
            return None

        new_exec = repair_executed if repair_executed is not None else existing["repair_executed"]
        new_status = verified_status if verified_status is not None else existing["verified_status"]
        new_notes = verification_notes if verification_notes is not None else existing["verification_notes"]
        exec_int = 1 if new_exec else 0

        query = """
            UPDATE solutions
            SET repair_executed = ?, verified_status = ?, verification_notes = ?
            WHERE id = ?;
        """
        with self.db.get_connection() as conn:
            conn.execute(query, (exec_int, new_status, new_notes, solution_id))

        return self.get(solution_id)

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """List all solutions associated with a specific session."""
        query = "SELECT * FROM solutions WHERE session_id = ? ORDER BY created_at ASC;"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["repair_executed"] = bool(item["repair_executed"])
                results.append(item)
            return results
