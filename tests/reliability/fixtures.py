"""WinFix AI — Reliability Test Fixtures (Phase 33)."""

import sqlite3
from typing import Any, Dict, Optional
import uuid


class MockTelemetryDB:
    """In-memory SQLite database providing complete Phase 0-32 schema for stress testing."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._setup_schema()

    def _setup_schema(self):
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'tutor',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                step_id INTEGER NOT NULL DEFAULT 0,
                workflow_state TEXT NOT NULL,
                current_step_index INTEGER NOT NULL DEFAULT 0,
                domain TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                schema_version TEXT NOT NULL DEFAULT '1.0'
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                state_before TEXT NOT NULL,
                state_after TEXT NOT NULL,
                tool_id TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_records (
                execution_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                step_id INTEGER NOT NULL DEFAULT 0,
                tool_name TEXT NOT NULL,
                argument_hash TEXT NOT NULL,
                authorization_hash TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                execution_status TEXT NOT NULL DEFAULT 'STARTED',
                verification_status TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_events (
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


def create_test_session_context(prefix: str = "sess") -> Dict[str, Any]:
    """Generate a deterministic session metadata dictionary."""
    sess_id = f"{prefix}_{uuid.uuid4().hex[:8]}"
    wf_id = f"wf_{uuid.uuid4().hex[:8]}"
    return {
        "session_id": sess_id,
        "workflow_id": wf_id,
        "domain": "NETWORK",
    }
