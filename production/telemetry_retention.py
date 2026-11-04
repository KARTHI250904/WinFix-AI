"""WinFix AI — Telemetry Retention & Cleanup Manager (Phase 32).

Provides bounded, privacy-compliant, transactional cleanup of historical telemetry events.
Guarantees:
  - Bounded SQLite growth (age-based and count-based ceilings).
  - Parameterized SQL with transactional rollback.
  - Never deletes active workflow checkpoints or required recovery states prematurely.
"""

from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("winfix.TELEMETRY_RETENTION")


class TelemetryRetentionManager:
    """Manages pruning and bounded storage of local telemetry records."""

    def __init__(self, db_manager: Optional[Any] = None):
        self._db_manager = db_manager

    def _get_connection(self):
        """Get database connection safely."""
        if self._db_manager is not None:
            return self._db_manager.get_connection()
        try:
            from database.db import get_db
            return get_db().get_connection()
        except Exception:
            return None

    def cleanup_old_events(
        self,
        retention_days: int = 30,
        max_event_count: int = 50000,
    ) -> Dict[str, Any]:
        """Perform transactional age-based and count-based pruning of telemetry events."""
        start_time = time.perf_counter()
        conn = self._get_connection()
        if conn is None:
            return {
                "success": False,
                "deleted_count": 0,
                "remaining_count": 0,
                "duration_ms": 0,
                "reason": "Database connection unavailable",
            }

        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        deleted_by_age = 0
        deleted_by_count = 0

        try:
            cursor = conn.cursor()

            # 1. Prune events older than retention_days (excluding active checkpoints)
            cursor.execute(
                """
                DELETE FROM telemetry_events
                WHERE timestamp_utc < ?
                AND session_id NOT IN (
                    SELECT session_id FROM workflow_checkpoints
                )
                """,
                (cutoff_date,),
            )
            deleted_by_age = cursor.rowcount

            # 2. Check total row count and prune excess if above max_event_count
            cursor.execute("SELECT COUNT(*) FROM telemetry_events")
            current_count = cursor.fetchone()[0]

            if current_count > max_event_count:
                excess = current_count - max_event_count
                cursor.execute(
                    """
                    DELETE FROM telemetry_events
                    WHERE id IN (
                        SELECT id FROM telemetry_events
                        WHERE session_id NOT IN (SELECT session_id FROM workflow_checkpoints)
                        ORDER BY timestamp_utc ASC
                        LIMIT ?
                    )
                    """,
                    (excess,),
                )
                deleted_by_count = cursor.rowcount

            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM telemetry_events")
            remaining_count = cursor.fetchone()[0]
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            total_deleted = deleted_by_age + deleted_by_count
            logger.info(f"Telemetry cleanup completed: {total_deleted} pruned, {remaining_count} remaining in {duration_ms}ms")

            return {
                "success": True,
                "deleted_count": total_deleted,
                "deleted_by_age": deleted_by_age,
                "deleted_by_count": deleted_by_count,
                "remaining_count": remaining_count,
                "duration_ms": duration_ms,
            }

        except Exception as ex:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"Telemetry retention cleanup failed: {ex}")
            return {
                "success": False,
                "deleted_count": 0,
                "remaining_count": -1,
                "duration_ms": int((time.perf_counter() - start_time) * 1000),
                "error": str(ex),
            }


# Global singleton instance
default_telemetry_retention = TelemetryRetentionManager()
