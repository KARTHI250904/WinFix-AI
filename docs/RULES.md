# WinFix AI — Engineering and Safety Rules

## 1. General Rules

1. Build for Windows first (Windows 10 / 11).
2. Use Python (Python 3.12 preferred baseline).
3. Use SQLite with parameterized queries.
4. Use Streamlit for the user interface.
5. Use Ollama for local AI inference with `gemma4:12b` as the default configurable model.
6. Keep all core troubleshooting operations offline-first.
7. Prefer small, testable, maintainable Python modules over large external frameworks.

---

## 2. Core AI & Shell Safety Rules

1. **`LLM != Windows Shell`**: The language model is a reasoning and planning component, not an operating-system shell.
2. **No Arbitrary Commands**: Never pass raw LLM output or arbitrary command strings into:
   * `os.system()`
   * `subprocess.run()`
   * `subprocess.Popen()`
   * PowerShell / CMD prompts
3. **No Generic `run_command`**: Never create a generic `run_command(command)` tool or allow the LLM to generate unrestricted shell scripts.
4. **Explicit Tool Registry**: All Windows operations must be predefined, explicitly registered Python tools.

---

## 3. Tool Architecture Rules

Every tool must define:
* `name`: Unique identifier
* `domain`: Troubleshooting area
* `description`: Clear purpose
* `risk`: `SAFE` | `MEDIUM` | `HIGH`
* `requires_admin`: Boolean flag
* `automatic_allowed`: Boolean flag
* `verification_tool`: Name of the corresponding verification tool (for repairs)

---

## 4. Risk Level Rules

### SAFE
* Read-only diagnostics and non-destructive inspections.
* May execute automatically in Autopilot mode.
* Must run without administrator elevation whenever possible.

### MEDIUM
* Controlled, reversible modifications to system state (e.g. restarting a service, flushing DNS cache, resetting an adapter).
* Always requires user confirmation in Personal Tutor mode.
* Requires user confirmation and elevation prompting in Autopilot mode.

### HIGH
* Potentially destructive, risky, or security-sensitive actions (e.g. deleting files, modifying registry, disabling security protections).
* **Strictly blocked from automatic execution.**

---

## 5. Administrator & UAC Elevation Rules

1. **Un-elevated Default**: The Streamlit application must not run permanently as Administrator by default.
2. **Controlled Elevation**: MEDIUM tools requiring administrative privileges must prompt the user with a clear explanation, obtain confirmation, and invoke an isolated, controlled elevation helper.
3. **Strict Validation**: Elevation helpers must validate tool arguments strictly against an allowlist before execution.

---

## 6. Prohibited Actions (No Destructive Automation)

WinFix AI must never automatically:
* Disable Windows Defender, real-time protection, or antivirus exclusions.
* Disable Windows Firewall or tamper with security policies.
* Delete user personal files (Documents, Desktop, Downloads, Pictures, Videos).
* Format drives or partitions.
* Modify arbitrary registry values without explicit approved tool implementation.
* Uninstall drivers automatically.
* Execute unverified downloaded scripts or binaries.

---

## 7. Diagnosis Before Repair Rule

* The application must diagnose and gather empirical evidence before attempting repairs.
* Never jump directly from a user symptom to a system reset without running diagnostic tools.

---

## 8. Verification & Honesty Rules

1. **Execution $\neq$ Success**: The application must never claim a problem is fixed simply because a command completed with exit code 0.
2. **Verification Required**: Every repair must run a verification check and report one of: `Fixed`, `Not fixed`, `Partially fixed`, or `Unable to verify`.
3. **Never Fake Results**: The AI must never invent diagnostic findings or claim success without empirical tool evidence.

---

## 9. Dependency & Scope Rules

1. **No Premature Dependencies**: Voice (e.g. speech-to-text) and vision/screenshot dependencies must not be added until their designated phases (Phase 18 and Phase 19).
2. **No Overbuilding**: Do not introduce LangChain, LangGraph, vector databases, PostgreSQL, Redis, or cloud AI services unless explicitly justified.

---

## 10. Database Rules

1. Use parameterized queries for all SQLite interactions.
2. Never concatenate raw strings into SQL statements.
3. Keep database logic isolated in `database/` repository modules.
4. Never call SQLite directly from Streamlit UI components.

---

## 11. Coding Standards

* Use type hints for all function signatures.
* Keep modules and functions small, focused, and testable.
* Standardize tool return schemas with explicit success, data, error, and duration fields.
* Never swallow exceptions silently; return structured error objects.

---

## 12. Canonical Task Roadmap Rule

Always work on the smallest unfinished task defined in `docs/TASKS.md` following the canonical 23-phase sequence. Do not skip phases or jump ahead without explicit instructions.
