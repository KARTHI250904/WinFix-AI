"""WinFix AI — Telemetry Retention & Pruning Tests (Phase 32)."""

from datetime import datetime, timedelta, timezone
import pytest
import sqlite3
import uuid

from production.telemetry_models import TelemetryEventType
from production.telemetry_retention import TelemetryRetentionManager


class MockDBManager:
    """In-memory SQLite connection provider for retention testing."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._setup_schema()

    def _setup_schema(self):
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE workflow_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE telemetry_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                timestamp_utc TIMESTAMP NOT NULL,
                event_type TEXT NOT NULL,
                component TEXT NOT NULL,
                schema_version TEXT NOT NULL DEFAULT '1.0',
                severity TEXT NOT NULL DEFAULT 'INFO',
                duration_ms INTEGER,
                domain TEXT,
                tool_name TEXT,
                failure_type TEXT NOT NULL DEFAULT 'NONE',
                outcome TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self._conn.commit()

    def get_connection(self):
        return self._conn


def test_retention_age_pruning():
    db = MockDBManager()
    manager = TelemetryRetentionManager(db_manager=db)
    conn = db.get_connection()
    cursor = conn.cursor()

    old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    recent_date = datetime.now(timezone.utc).isoformat()

    # Insert old event and recent event
    cursor.execute(
        "INSERT INTO telemetry_events (event_id, session_id, timestamp_utc, event_type, component) VALUES (?, ?, ?, ?, ?)",
        ("ev_old", "sess_old", old_date, "SESSION_STARTED", "core"),
    )
    cursor.execute(
        "INSERT INTO telemetry_events (event_id, session_id, timestamp_utc, event_type, component) VALUES (?, ?, ?, ?, ?)",
        ("ev_new", "sess_new", recent_date, "SESSION_STARTED", "core"),
    )
    conn.commit()

    stats = manager.cleanup_old_events(retention_days=30, max_event_count=100)
    assert stats["success"] is True
    assert stats["deleted_by_age"] == 1
    assert stats["remaining_count"] == 1

    cursor.execute("SELECT event_id FROM telemetry_events")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "ev_new"


def test_retention_preserves_active_checkpoints():
    db = MockDBManager()
    manager = TelemetryRetentionManager(db_manager=db)
    conn = db.get_connection()
    cursor = conn.cursor()

    old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

    # Insert checkpoint for session
    cursor.execute(
        "INSERT INTO workflow_checkpoints (checkpoint_id, session_id) VALUES (?, ?)",
        ("chk_1", "active_sess"),
    )
    # Insert old event for active session
    cursor.execute(
        "INSERT INTO telemetry_events (event_id, session_id, timestamp_utc, event_type, component) VALUES (?, ?, ?, ?, ?)",
        ("ev_active_old", "active_sess", old_date, "SESSION_STARTED", "core"),
    )
    conn.commit()

    stats = manager.cleanup_old_events(retention_days=30, max_event_count=100)
    assert stats["success"] is True
    assert stats["deleted_by_age"] == 0
    assert stats["remaining_count"] == 1


def test_retention_count_limit_pruning():
    db = MockDBManager()
    manager = TelemetryRetentionManager(db_manager=db)
    conn = db.get_connection()
    cursor = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()
    for i in range(25):
        cursor.execute(
            "INSERT INTO telemetry_events (event_id, session_id, timestamp_utc, event_type, component) VALUES (?, ?, ?, ?, ?)",
            (f"ev_{i}", f"sess_{i}", now, "WORKFLOW_STARTED", "core"),
        )
    conn.commit()

    # Prune to max 10 events
    stats = manager.cleanup_old_events(retention_days=365, max_event_count=10)
    assert stats["success"] is True
    assert stats["deleted_by_count"] == 15
    assert stats["remaining_count"] == 10
