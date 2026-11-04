# WinFix AI — System Architecture (v1.0.0 Production Release)

## High-Level Pipeline

```text
User Request (Text / Voice / Screenshot)
                   ↓
Input Validation & Privacy Sanitization
                   ↓
Agent Core / Personal Tutor / Autopilot Orchestrator
                   ↓
Local Knowledge Base Search (SQLite / FTS5)
                   ↓
Structured Tool Request Formulation
                   ↓
Central Tool Registry (59 Allowlisted Handlers)
                   ↓
SafetyEngine (Risk Evaluation & Bounds Checking)
                   ↓
Cryptographic User Confirmation (MEDIUM Risk Tools)
                   ↓
Deterministic Windows Tool Execution (Direct Win32 / API)
                   ↓
Verification Handlers (State Comparison)
                   ↓
SQLite Audit Trail & Educational Synthesis
                   ↓
Streamlit UI Presentation
```

---

## Subsystem Breakdown

1. **`production/`**:
   - `config.py`: Strongly-typed configuration (`ProductionConfig`) with production defaults.
   - `paths.py`: Controlled AppData directories (`Data/`, `Logs/`, `Config/`, `Temp/`) with path traversal guards.
   - `setup.py`: Idempotent first-run environment initialization and seed knowledge loading.
   - `health_check.py`: Pre-flight system health evaluator (`HealthCheckEngine`) validating runtime, database, tools, Ollama, and media layers.
   - `logging.py`: Centralized rotating logging with automated privacy sanitization.
   - `crash_handler.py`: Safe exception boundaries preventing raw stack trace exposure or automated repairs after crash.
   - `lifecycle.py`: Controlled restart validation, transactional schema migrations, and uninstall retention policies.

2. **`agent/`**:
   - `tool_registry.py`: Authoritative catalog of 59 verified Windows tools.
   - `safety.py`: Fail-closed policy enforcement and confirmation token binding.
   - Domain orchestrators: Network, Storage, Performance, Services, Bluetooth, Windows Update, Defender, Application Crashes.

3. **`database/` & `knowledge/`**:
   - `db.py`: SQLite connection pooling with WAL mode and busy timeouts.
   - `knowledge_repository.py`: CRUD and search layer for 9 structured troubleshooting articles.
   - `knowledge_search.py`: Deterministic token-ranked query engine with FTS5.

4. **`modes/`**:
   - `personal_tutor.py`: Educational mentor mode with factual evidence separation.
   - `autopilot.py`: Multi-step plan generator with cryptographic hash verification and precondition guards.

5. **`ai/`**:
   - `ollama_client.py`: Local Gemma LLM interface with fallback heuristics.
   - `screenshot_analyzer.py`: Vision analysis and diagnostic mapping.
   - `voice_transcriber.py`: Local offline Speech-to-Text transcriber.
