# WinFix AI — Project Memory

## Project Identity

* **Project Name:** WinFix AI
* **Purpose:** Offline-first AI-powered Windows troubleshooting assistant.

---

## Fixed Technology Decisions

* **Programming Language:** Python (Python 3.12 preferred baseline)
* **Frontend:** Streamlit
* **Database:** SQLite (parameterized queries only)
* **Local AI Runtime:** Ollama
* **Primary AI Model:** `gemma4:12b` (configured centrally in `config.py`)
* **Operating System:** Windows 10 / 11
* **IDE / Development:** VS Code / Antigravity

---

## Operating Modes

1. **Personal Tutor:** Educational, step-by-step, plain-language explanations, mandatory user confirmation before repairs.
2. **Autopilot:** Autonomous, runs SAFE diagnostics and SAFE repairs automatically, prompts for MEDIUM repairs, blocks HIGH-risk operations, verifies outcomes.

---

## Supported Input Types

1. **Text:** Natural language descriptions (Phase 0+)
2. **Screenshot:** Local multimodal vision evidence analysis (Phase 18)
3. **Voice:** Local microphone capture + speech-to-text (Phase 19)

*Note: Voice and vision packages are kept out of requirements until their implementation phases.*

---

## Critical Architecture Decisions

1. **`LLM != Windows Shell`**: The LLM is a reasoning and planning agent. It must never execute arbitrary shell/PowerShell commands or generic `run_command()` functions.
2. **Explicit Tool Registry & Safety Validator**: Every Windows action is an explicitly implemented, allowlisted Python tool with defined risk levels (`SAFE`, `MEDIUM`, `HIGH`).
3. **Administrator / UAC Strategy**:
   * Streamlit app does not run permanently as Administrator by default.
   * SAFE tools execute un-elevated.
   * MEDIUM tools requiring admin rights require explicit user confirmation and execute via a controlled elevation mechanism.
   * HIGH-risk actions are permanently blocked.
4. **Mandatory Repair Verification**: A repair is never deemed successful without post-repair verification checks.

---

## Canonical 23-Phase Roadmap

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

## Current Development Stage

**Phase 0 — Foundation** (Awaiting user approval before implementing).
