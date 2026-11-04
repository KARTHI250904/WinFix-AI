-- WinFix AI SQLite Baseline Schema

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'tutor',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    input_type TEXT NOT NULL DEFAULT 'text',
    category TEXT,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS diagnostics (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_executions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    requires_admin INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_message TEXT,
    result_json TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS solutions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    proposed_repair TEXT,
    repair_executed INTEGER NOT NULL DEFAULT 0,
    verified_status TEXT NOT NULL DEFAULT 'unverified',
    verification_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    rating INTEGER,
    comments TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge Base Tables (Phase 19)
CREATE TABLE IF NOT EXISTS knowledge_articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence REAL NOT NULL DEFAULT 1.0,
    platform TEXT NOT NULL DEFAULT 'Windows 10/11',
    source TEXT NOT NULL DEFAULT 'Built-in',
    version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_symptoms (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    symptom_text TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_causes (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    cause_text TEXT NOT NULL,
    likelihood TEXT DEFAULT 'POSSIBLE',
    FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_diagnostic_steps (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    step_text TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_tool_links (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    tool_role TEXT NOT NULL DEFAULT 'DIAGNOSTIC',
    FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_verification_steps (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    step_text TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes (Phase 24)
CREATE INDEX IF NOT EXISTS idx_problems_session ON problems(session_id);
CREATE INDEX IF NOT EXISTS idx_diagnostics_session ON diagnostics(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_session ON tool_executions(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_tool ON tool_executions(tool_name);
CREATE INDEX IF NOT EXISTS idx_solutions_session ON solutions(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_articles_category ON knowledge_articles(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_articles_enabled ON knowledge_articles(enabled);
CREATE INDEX IF NOT EXISTS idx_knowledge_symptoms_article ON knowledge_symptoms(article_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_causes_article ON knowledge_causes(article_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_diagnostic_steps_article ON knowledge_diagnostic_steps(article_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_tool_links_article ON knowledge_tool_links(article_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_verification_steps_article ON knowledge_verification_steps(article_id);

-- Production Recovery & Checkpointing Tables (Phase 31)
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
    schema_version TEXT NOT NULL DEFAULT '1.0',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recovery_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    state_before TEXT NOT NULL,
    state_after TEXT NOT NULL,
    tool_id TEXT,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

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
    verification_status TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_session ON workflow_checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_workflow ON workflow_checkpoints(workflow_id);
CREATE INDEX IF NOT EXISTS idx_recovery_events_session ON recovery_events(session_id);
CREATE INDEX IF NOT EXISTS idx_execution_records_session ON execution_records(session_id);
CREATE INDEX IF NOT EXISTS idx_execution_records_lookup ON execution_records(session_id, workflow_id, tool_name);

-- Observability, Diagnostics Telemetry & Reliability Analytics (Phase 32)
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




