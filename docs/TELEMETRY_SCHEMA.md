# WinFix AI — Telemetry Database Schema (Phase 32)

## SQLite Telemetry Table

The telemetry event store is backed by SQLite table `telemetry_events`:

```sql
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry_events(session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_events(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_telemetry_event_type ON telemetry_events(event_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_domain ON telemetry_events(domain);
CREATE INDEX IF NOT EXISTS idx_telemetry_tool ON telemetry_events(tool_name);
CREATE INDEX IF NOT EXISTS idx_telemetry_failure ON telemetry_events(failure_type);
```

---

## Column Descriptions

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Internal autoincrement primary key for efficient pagination and FIFO pruning. |
| `event_id` | TEXT UNIQUE | Canonical UUID uniquely identifying the operational event. |
| `session_id` | TEXT | Identifier of the troubleshooting session. Foreign key to `sessions(id)`. |
| `timestamp_utc` | TIMESTAMP | ISO 8601 UTC timestamp of event occurrence. |
| `event_type` | TEXT | Structured event taxonomy classification. |
| `component` | TEXT | Source subsystem (e.g., `workflow_engine`, `diagnostic_engine`, `recovery_manager`). |
| `schema_version`| TEXT | Version of event metadata payload (default `'1.0'`). |
| `severity` | TEXT | Severity tier (`INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `duration_ms` | INTEGER | Execution latency or phase duration in milliseconds (if applicable). |
| `domain` | TEXT | Diagnostic domain (e.g., `NETWORK`, `PERFORMANCE`, `STORAGE`, `SERVICES`). |
| `tool_name` | TEXT | Registered tool name involved in the event (if applicable). |
| `failure_type` | TEXT | Deterministic failure taxonomy classification (`NONE` if successful). |
| `outcome` | TEXT | High-level status or state transition target (e.g., `COMPLETED`, `UNRESOLVED`). |
| `metadata_json` | TEXT | JSON string containing sanitized, bounded metadata dictionary. |
| `created_at` | TIMESTAMP | Database record insertion timestamp. |
