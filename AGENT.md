# WinFix AI — Antigravity Master Instructions

## Role

You are the primary software development agent for WinFix AI.

WinFix AI is an offline-first Windows troubleshooting AI assistant.

The project uses:

* Python (Python 3.12 preferred baseline)
* Streamlit
* SQLite
* Ollama
* `gemma4:12b`

---

# 1. Read Before Coding

Before modifying the project, read:

```text
README.md
docs/PRD.md
docs/ARCHITECTURE.md
docs/RULES.md
docs/DESIGN.md
docs/TASKS.md
docs/MEMORY.md
```

These files define the current project requirements.

---

# 2. Source of Truth

Use the documentation as the project source of truth.

Do not invent a different architecture without first identifying why the existing architecture is insufficient.

If a new requirement changes architecture:

1. Explain the change.
2. Update the appropriate documentation.
3. Then implement the change.

---

# 3. Canonical Development Sequence

Never attempt to implement the entire project in one task. Work incrementally following the canonical roadmap:

```text
Phase 0  - Foundation
Phase 1  - System Information
Phase 2  - SQLite Foundation
Phase 3  - Read-only Windows Tools
Phase 4  - Tool Registry + Safety
Phase 5  - Ollama/Gemma Agent Core
Phase 6  - Network Diagnostics
Phase 7  - Network Repairs + Verification
Phase 8  - Performance
Phase 9  - Storage
Phase 10 - Windows Services
Phase 11 - Bluetooth
Phase 12 - Printer
Phase 13 - Windows Update
Phase 14 - Windows Defender
Phase 15 - Application Crashes
Phase 16 - Personal Tutor
Phase 17 - Autopilot
Phase 18 - Screenshot
Phase 19 - Voice
Phase 20 - SQLite Knowledge System
Phase 21 - UI/UX Polish
Phase 22 - Comprehensive Testing
```

---

# 4. Model

The default Ollama model is:

```text
gemma4:12b
```

The model name must be configurable in `config.py`.

Do not hard-code it throughout the codebase.

If the configured model is unavailable, provide a clear error message.

Do not silently switch to a cloud model.

---

# 5. Project Location & Structure

The Python virtual environment is:

```text
WinFix-AI/.venv/
```

Do not put source code inside `.venv`.

Standard directory layout:

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

# 6. AI Architecture Principle

Gemma is responsible for:

* Understanding natural language.
* Reasoning.
* Creating diagnostic plans.
* Selecting approved tools from the registry.
* Interpreting tool results.
* Explaining results in plain English.

Gemma is NOT responsible for:

* Executing arbitrary Windows commands (`LLM != Windows Shell`).
* Directly accessing the operating system.
* Generating executable PowerShell or shell scripts for unrestricted execution.

---

# 7. Windows Tool Architecture

Every Windows capability must be implemented as an explicit registered Python tool.

Workflow:

```text
User
 ↓
Gemma
 ↓
Tool request (JSON)
 ↓
Tool registry
 ↓
Safety validation
 ↓
Python tool
 ↓
Windows API / Subprocess
 ↓
Structured result
 ↓
Gemma explanation
```

Never bypass the registry or safety validator.

---

# 8. Administrator & UAC Elevation Strategy

The administrator elevation strategy must be explicitly designed and controlled:

1. **Un-elevated Default:** SAFE tools and read-only diagnostics run without elevation whenever possible.
2. **Controlled Elevation for MEDIUM Tools:** MEDIUM-risk repair operations that require administrative privileges must ask for explicit user confirmation and invoke a dedicated, controlled elevation mechanism (e.g. isolated elevated worker).
3. **HIGH-Risk Blocked:** HIGH-risk operations remain strictly blocked from automatic execution.
4. **No Permanent Root/Admin UI:** The Streamlit application must NOT simply run permanently as Administrator as the default architecture.

---

# 9. Python Compatibility

* Target Python version must be selected deliberately.
* **Python 3.12** is the preferred baseline for maximum library and binary wheel compatibility across Windows environments.
* Voice and vision dependencies are kept out of the initial requirements until their dedicated implementation phases (Phase 18 and Phase 19).

---

# 10. Safety & Risk Model

Every tool registered in the system must define:

```python
{
    "name": str,
    "domain": str,
    "description": str,
    "risk": "SAFE" | "MEDIUM" | "HIGH",
    "requires_admin": bool,
    "automatic_allowed": bool,
    "verification_tool": str | None
}
```

* **SAFE:** Read-only diagnostics and safe inspections (allowed automatically).
* **MEDIUM:** Modifies system state in a reversible way (requires user confirmation in Tutor mode, and appropriate confirmation + elevation in Autopilot).
* **HIGH:** Destructive or security-sensitive operations (strictly blocked from automatic execution).

Never automatically:
* Disable Defender or Firewall.
* Delete arbitrary user files (Desktop, Documents, Downloads).
* Modify arbitrary registry values.
* Uninstall drivers automatically.

---

# 11. Autopilot Mode

* Automatically creates diagnostic plans and runs SAFE diagnostic tools.
* Automatically performs approved SAFE repairs.
* Requires explicit user confirmation for MEDIUM-risk repairs.
* Blocks HIGH-risk operations.
* Displays real-time progress steps.
* Always performs and reports verification after repairs.

---

# 12. Personal Tutor Mode

* Explains the problem in accessible non-technical language.
* Explains why each check is being run and what technical terms mean.
* Always asks for user permission before any repair action.
* Explains repair actions and verified outcomes.
* Provides expandable "Technical Details" for advanced users.

---

# 13. Screenshot Input

* Screenshots are treated as **evidence**, not proof.
* When a screenshot indicates an issue, the agent must verify the current system state using approved diagnostic tools before proposing repairs.

---

# 14. Voice Input

* Follows: Microphone $\rightarrow$ Local Speech-to-Text $\rightarrow$ Text $\rightarrow$ WinFix Agent.
* Voice inputs use the exact same agent planning and safety architecture as text.

---

# 15. Database Layer

* All persistence must go through the database repository layer.
* Strictly use parameterized SQL queries to prevent SQL injection.
* Never access SQLite directly from the Streamlit UI layer.

---

# 16. Verification Contract

* A command returning exit code 0 or completing does NOT mean the problem is fixed.
* Every repair must execute its corresponding verification tool.
* Final UI results must report one of: `Fixed`, `Not fixed`, `Partially fixed`, or `Unable to verify`.
* The AI must never claim success without verification evidence.

---

# 17. Error Handling & Tool Return Format

Tools must return a standardized dictionary:

```python
{
    "success": bool,
    "tool": str,
    "data": dict | None,
    "error": dict | None,
    "duration_ms": int
}
```

Never hide failures from the agent or the user.

---

# 18. Testing Philosophy

Every tool, safety check, and repair must be tested for:

* Normal success
* Timeout
* Permission / elevation failure
* Unexpected Windows command output
* Safety policy enforcement
* Verification accuracy

---

# 19. Task Execution Protocol

For every task:

1. Read documentation.
2. Inspect existing code.
3. Identify affected modules.
4. Implement the smallest necessary change.
5. Run tests.
6. Verify syntax and imports.
7. Run the application when practical.
8. Update `docs/TASKS.md`.
9. Report status, files changed, and next recommended step.

---

# 20. Do Not Overbuild

Do not introduce LangChain, LangGraph, vector databases, PostgreSQL, Redis, Docker, or cloud AI services unless the architecture demonstrates a concrete need.

---

# 21. Current Development Rule

Always implement the smallest unfinished task from `docs/TASKS.md`. Do not jump ahead without explicit instruction.
