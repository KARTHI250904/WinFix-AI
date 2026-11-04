# WinFix AI — User Guide (v1.0.0 Production Release)

## Introduction

**WinFix AI** is an offline-first Windows troubleshooting assistant and personal tutor designed to diagnose, explain, and resolve Windows issues securely.

---

## The 5 Operating Modes

### 1. 🔍 Diagnostic & Repair Assistant
The primary conversational troubleshooting engine.
* **How to use**: Type a description of your issue (e.g., *"My internet is disconnected"* or *"Print spooler is stopped"*).
* **Diagnostic Phase**: WinFix AI executes safe, read-only Windows tools to collect factual system evidence.
* **Repair Recommendation**: When a repair is available, WinFix AI displays the action along with its risk level, required parameters, and security implications.
* **Confirmation Gate**: All repair operations require explicit user confirmation before execution.
* **Deterministic Verification**: After repair execution, WinFix AI verifies whether the system recovered.

### 2. 🎓 Personal Tutor Mode
An educational troubleshooting mentor.
* **How to use**: Ask any Windows technical question or explore diagnostics without triggering repairs.
* **Evidence Separation**: Plain-language explanations cleanly separate facts, severity, probable causes, and safety notes.
* **Local Knowledge Base**: Powered by 9 verified troubleshooting knowledge articles stored in local SQLite.

### 3. 🤖 Autopilot Mode
Bounded, verified multi-step autonomous troubleshooting.
* **How to use**: Enter a high-level troubleshooting goal (e.g., *"Diagnose and repair network adapters and DNS"*).
* **Deterministic Plan**: Autopilot formulates an explicit sequence of up to 5 steps with strict preconditions.
* **Cryptographic Authorization**: Plans are cryptographically hashed and bound to the session.
* **Fail-Closed Execution**: If any step encounters an unexpected condition or precondition failure, execution stops immediately.

### 4. 📷 Screenshot Diagnostics
Visual inspection for error dialogs, blue screens, and system settings.
* **How to use**: Upload a `.png` or `.jpg` screenshot of an error message, dialog, or device manager.
* **Privacy Isolation**: Raw image pixels are processed in memory and never stored permanently on disk.
* **Structured Observation**: Converts visual elements into structured diagnostic evidence mapped to allowlisted tools.

### 5. 🎤 Voice Diagnostics
Hands-free spoken troubleshooting.
* **How to use**: Record or upload an audio clip describing your computer problem.
* **Local STT**: Transcribed locally using offline speech-to-text models.
* **Privacy Sanitization**: Transcripts are automatically scrubbed of personal paths, emails, and credentials before processing.

---

## Security & Confirmation Model

1. **SAFE Tools (49)**: Executed automatically (read-only system inspections).
2. **MEDIUM Tools (10)**: Require explicit, one-time confirmation tokens signed by the user.
3. **HIGH Risk**: Strictly blocked by the SafetyEngine. No arbitrary command execution is permitted.
4. **Security Invariant**: `LLM != Windows Shell`, `UI != Execution Layer`. Packaging does not alter this boundary.

---

## Launcher Options

Run `winfix_launcher.exe` or `python winfix_launcher.py` with the following flags:

* `--port <int>` : Custom port (default: 8501, bound strictly to `127.0.0.1`).
* `--check-only` : Execute pre-flight integrity and health check, report readiness status, and exit.
* `--migrate`    : Apply pending database schema migrations safely and exit.
* `--setup-only` : Initialize `%LOCALAPPDATA%\WinFixAI` folders and baseline SQLite database.
* `--headless`   : Run server without automatically opening default browser window.
