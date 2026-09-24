# WinFix AI — System Architecture

## 1. Architecture Philosophy

WinFix AI uses a modular, layered architecture with strict separation of concerns.

**Fundamental Rule:** `LLM != Windows Shell`. The AI model is a reasoning and planning component. It is never directly exposed to the operating system shell and cannot execute arbitrary commands.

The architecture cleanly isolates:
1. **User Interface:** Streamlit presentation layer.
2. **Input Normalization:** Text, Voice (Phase 19), Screenshot (Phase 18).
3. **AI Planning & Reasoning:** Ollama client with `gemma4:12b`.
4. **Agent Orchestration:** Diagnostic planning, state machine, Tutor/Autopilot modes.
5. **Tool Registry & Safety Validator:** Explicit tool definitions, risk enforcement, and UAC elevation controls.
6. **Windows Execution Layer:** Dedicated Python modules wrapping safe system APIs and utilities.
7. **Verification Layer:** Post-repair validation engines.
8. **Persistence Layer:** SQLite database and local knowledge store.

---

## 2. High-Level Architecture Diagram

```text
                     USER
                       |
         +-------------+-------------+
         |             |             |
        Text      Voice (Ph 19) Screenshot (Ph 18)
         |             |             |
         +-------------+-------------+
                       |
               Input Processor
                       |
                       v
               WinFix Agent Core
                       |
           +-----------+-----------+
           |                       |
      Tutor Mode              Autopilot Mode
           |                       |
           +-----------+-----------+
                       |
                  AI Planner
                       |
                 Ollama / Gemma
                   gemma4:12b
                       |
               Structured Tool Plan (JSON)
                       |
               Safety Validator Layer
              (Risk + UAC Permission)
                       |
               Windows Tool Registry
                       |
       +---------------+---------------+
       |               |               |
   System Tools   Network Tools   Service Tools ...
       |               |               |
       +---------------+---------------+
                       |
             Structured Results (JSON)
                       |
                       v
               Verification Engine
                       |
                  AI Synthesis
                       |
              Plain-English Outcome
                       |
                 Streamlit UI
```

---

## 3. Technology Stack

* **Programming Language:** Python (Python 3.12 preferred baseline)
* **Frontend:** Streamlit
* **Local AI Runtime:** Ollama
* **Default AI Model:** `gemma4:12b` (centrally configured in `config.py`)
* **Persistence:** SQLite
* **Windows Integration:** Python standard library, `psutil`, `pywin32`, Windows APIs
* **Target Operating System:** Windows 10 / 11

---

## 4. Standard Directory Layout

```text
WinFix-AI/
├── .venv/
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── RULES.md
│   ├── DESIGN.md
│   ├── TASKS.md
│   └── MEMORY.md
├── ai/
│   ├── __init__.py
│   ├── ollama_client.py
│   └── prompts.py
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── planner.py
│   ├── tool_registry.py
│   ├── tool_executor.py
│   ├── safety.py
│   └── schemas.py
├── database/
│   ├── __init__.py
│   ├── db.py
│   ├── schema.sql
│   └── repository.py
├── input/
│   ├── __init__.py
│   ├── text_input.py
│   ├── voice_input.py
│   └── screenshot.py
├── modes/
│   ├── __init__.py
│   ├── tutor.py
│   └── autopilot.py
├── windows/
│   ├── __init__.py
│   ├── system.py
│   ├── network.py
│   ├── performance.py
│   ├── storage.py
│   ├── services.py
│   ├── bluetooth.py
│   ├── printer.py
│   ├── windows_update.py
│   ├── defender.py
│   └── applications.py
├── knowledge/
│   ├── __init__.py
│   ├── troubleshooting.db
│   └── seed_data.py
├── tests/
├── assets/
├── app.py
├── config.py
├── requirements.txt
├── .gitignore
├── AGENT.md
└── README.md
```

---

## 5. Component Responsibilities

### 5.1 Streamlit Presentation Layer (`app.py`)
* Manages UI state, inputs, cards, and animations.
* Renders Tutor dialogs and Autopilot progress bars.
* Exposes expandable "Technical Details" without cluttering the primary view.
* Never contains direct Windows command execution or direct raw SQL.

### 5.2 Input Layer (`input/`)
* Normalizes text, validates image files, and captures audio inputs.
* Transcribes voice to text via local STT before passing to the agent.

### 5.3 AI Layer (`ai/`)
* Handles communication with the local Ollama runtime.
* Enforces structured JSON schemas for diagnostic planning and problem categorization.
* Provides graceful offline fallbacks and error handling.

### 5.4 Agent Layer (`agent/`)
* Orchestrates the troubleshooting loop: `Understand` $\rightarrow$ `Plan` $\rightarrow$ `Execute` $\rightarrow$ `Verify` $\rightarrow$ `Explain`.
* Manages Tutor vs. Autopilot execution rules.

### 5.5 Tool Registry & Safety Layer (`agent/tool_registry.py`, `agent/safety.py`)
* Central registry containing metadata for every allowed Windows tool.
* Validates every tool request before execution.
* Checks risk levels, user confirmation status, and elevation requirements.

### 5.6 Windows Tool Layer (`windows/`)
* Implements explicit, self-contained Python functions for each Windows diagnostic and repair action.
* Returns standardized structured dictionaries:
  ```json
  {
    "success": true,
    "tool": "get_ip_configuration",
    "data": { ... },
    "error": null,
    "duration_ms": 110
  }
  ```

### 5.7 Database Layer (`database/`)
* Manages SQLite connection and parameterized operations.
* Records session histories, tool execution logs, and resolution tracking.

---

## 6. Administrator & UAC Elevation Strategy

1. **Un-elevated Default:** The Streamlit application must not run permanently as Administrator by default. SAFE diagnostic tools execute with normal user privileges.
2. **Controlled Elevation:** When a repair tool requires elevation (`requires_admin = True`):
   * The agent pauses and explains to the user why administrative rights are needed.
   * In Tutor mode, the user explicitly confirms the action.
   * In Autopilot mode, the user is prompted for confirmation before elevation occurs.
   * Elevation is executed via an isolated helper mechanism with strict argument validation.
3. **HIGH-Risk Operations Blocked:** Destructive or high-risk operations (e.g. disabling Defender/Firewall, registry cleaning, arbitrary file deletion) are completely blocked regardless of elevation state.

---

## 7. Repair & Verification Contract

Every repair tool is paired with a corresponding verification tool:

```text
Problem Detected
      ↓
Pre-Repair State Recorded
      ↓
Execute Repair Tool
      ↓
Execute Verification Tool
      ↓
Compare Pre/Post State
      ↓
Confirm Resolution (Fixed / Not Fixed / Partially Fixed / Unable to Verify)
```

The AI is strictly prohibited from asserting success without verified empirical evidence.

---

## 8. Canonical 23-Phase Implementation Sequence

* **Phase 0:** Foundation
* **Phase 1:** System Information
* **Phase 2:** SQLite Foundation
* **Phase 3:** Read-only Windows Tools
* **Phase 4:** Tool Registry + Safety
* **Phase 5:** Ollama/Gemma Agent Core
* **Phase 6:** Network Diagnostics
* **Phase 7:** Network Repairs + Verification
* **Phase 8:** Performance
* **Phase 9:** Storage
* **Phase 10:** Windows Services
* **Phase 11:** Bluetooth
* **Phase 12:** Printer
* **Phase 13:** Windows Update
* **Phase 14:** Windows Defender
* **Phase 15:** Application Crashes
* **Phase 16:** Personal Tutor
* **Phase 17:** Autopilot
* **Phase 18:** Screenshot
* **Phase 19:** Voice
* **Phase 20:** SQLite Knowledge System
* **Phase 21:** UI/UX Polish
* **Phase 22:** Comprehensive Testing
