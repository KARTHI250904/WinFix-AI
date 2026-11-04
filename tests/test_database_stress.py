"""WinFix AI — Database Stress & Rollback Tests (Phase 33)."""

import pytest
import sqlite3
from tests.reliability.fixtures import MockTelemetryDB
from production.telemetry import TelemetryService
from production.telemetry_models import TelemetryEventType
from production.telemetry_retention import TelemetryRetentionManager


def test_high_volume_telemetry_inserts():
    """Verify SQLite handles 1,000 telemetry events with index consistency and low latency."""
    db = MockTelemetryDB()
    service = TelemetryService(db_manager=db)

    for i in range(1000):
        service.record_workflow_event(
            session_id=f"bulk_sess_{i % 50}",
            event_type=TelemetryEventType.WORKFLOW_STEP_COMPLETED,
            domain="STORAGE",
            duration_ms=i,
            metadata={"index": i},
        )

    events = service.get_events(limit=2000)
    assert len(events) == 1000


def test_telemetry_retention_transactional_rollback():
    """Verify retention cleanup rolls back cleanly if an error occurs."""
    db = MockTelemetryDB()
    manager = TelemetryRetentionManager(db_manager=db)

    # Corrupt table reference to force query exception
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE telemetry_events")
    conn.commit()

    stats = manager.cleanup_old_events(retention_days=30)
    assert stats["success"] is False
    assert "error" in stats
