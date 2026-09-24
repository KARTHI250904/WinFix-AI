# WinFix AI

**Offline AI-powered Windows Troubleshooting Assistant

Tillnow phases 11 completed**

WinFix AI is a local, offline-first Windows troubleshooting assistant designed to help users diagnose, understand, repair, and verify common Windows computer problems safely.

The project combines:

* Python (Python 3.12 preferred baseline)
* Streamlit
* SQLite
* Ollama
* Gemma 4 12B (`gemma4:12b`)
* Windows diagnostic APIs and controlled system tools
* Local troubleshooting knowledge base
* Controlled AI tool execution & safety validation

The goal is to provide a simple, friendly experience for non-technical users while providing comprehensive technical details for advanced users.

---

## 1. Project Vision

WinFix AI acts as a personal local Windows support assistant. A user can describe an issue in natural language, speak via microphone, or provide an error screenshot.

WinFix AI systematically executes:

```text
User Problem
     ↓
Understand & Classify
     ↓
Diagnose (Safe Tools)
     ↓
Collect Evidence
     ↓
Identify Likely Cause
     ↓
Select Approved Action
     ↓
Confirm & Elevate (if needed)
     ↓
Repair
     ↓
Verify
     ↓
Explain Result
```

---

## 2. Core Principles

* **Safety First:** `LLM != Windows Shell`. The AI model is a reasoning engine and never executes arbitrary shell scripts or unrestricted commands.
* **Offline-First:** All core diagnostic reasoning, tools, and persistence operate completely offline without cloud dependencies.
* **Verification Required:** A repair is never deemed successful without post-repair verification.
* **Controlled Elevation:** Read-only diagnostics run without elevation. Operations requiring administrator privileges use explicit user confirmation and controlled elevation.
* **Understandable Explanations:** Non-technical summaries are presented by default; technical details remain accessible in expandable views.

---

## 3. Technology Stack

| Component | Technology |
| --- | --- |
| Programming Language | Python (Python 3.12 preferred baseline) |
| Frontend | Streamlit |
| Local AI Runtime | Ollama |
| AI Model | Gemma 4 12B (`gemma4:12b`), centrally configurable |
| Database | SQLite |
| Windows Integration | Python standard library, `psutil`, `pywin32`, Windows APIs |
| Target OS | Windows 10 / 11 |
| Internet Requirement | Not required for core operations |

---

## 4. Architecture Principle: Controlled Execution

WinFix AI enforces strict separation between AI reasoning and operating system execution:

```text
User
 ↓
Streamlit UI
 ↓
WinFix Agent Core
 ↓
Ollama (Gemma 4 12B)
 ↓
Structured Tool Request (JSON)
 ↓
Safety Validator & Risk Check
 ↓
Controlled Python Tool
 ↓
Windows OS / API
 ↓
Structured Result (JSON)
 ↓
Verification Tool
 ↓
Gemma Plain-English Explanation
 ↓
User
```

The LLM never directly invokes `subprocess`, PowerShell, or command prompts.

---

## 5. Operating Modes

### 5.1 Personal Tutor
* Educates and guides the user through each diagnostic step.
* Explains technical concepts in accessible language.
* Asks for explicit user permission before performing any repair.
* Explains the repair and verification results.

### 5.2 Autopilot
* Autonomous diagnostic and repair workflow with minimal user prompts.
* Automatically runs SAFE diagnostic tools and approved SAFE repairs.
* Requests user confirmation and elevation for MEDIUM-risk repairs.
* Blocks HIGH-risk operations.
* Shows real-time progress steppers and verified outcomes.

---

## 6. Supported Input Types

* **Text:** Natural language descriptions of computer issues.
* **Voice (Phase 19):** Local audio capture $\rightarrow$ local speech-to-text $\rightarrow$ normalized text input.
* **Screenshot (Phase 18):** Error dialog image $\rightarrow$ local multimodal vision analysis $\rightarrow$ verified by Windows diagnostic tools.

---

## 7. Troubleshooting Domains

1. **System Information:** Windows version, build, CPU, RAM, disk drives, uptime, architecture.
2. **Network Connectivity:** Wi-Fi, Ethernet, IP configuration, gateway, DNS resolution/cache, network adapters.
3. **Performance:** CPU/RAM/Disk utilization, top resource-consuming processes, slow system diagnosis.
4. **Storage:** Disk free space, drive health, safe allowlisted temporary file and cache investigation.
5. **Windows Services:** Status, startup configuration, and controlled restart of allowlisted services.
6. **Bluetooth:** Adapter detection, Bluetooth service status, device visibility, safe troubleshooting.
7. **Printer:** Status, print queue inspection, Print Spooler service state, controlled spooler restart, queue cleanup.
8. **Windows Update:** Service state, update error codes, connectivity checks, controlled service restart.
9. **Windows Defender:** Status, real-time protection, definition status (*read-only reporting only; never disabled*).
10. **Application Crashes:** Event log crash analysis, affected process diagnostics, safe recommendations.

---

## 8. Safety & Risk Architecture

Every tool in the system is explicitly registered with metadata:

```python
{
    "name": "restart_network_adapter",
    "domain": "network",
    "description": "Restart a specific network adapter",
    "risk": "MEDIUM",
    "requires_admin": True,
    "automatic_allowed": False,
    "verification_tool": "get_network_adapter_status"
}
```

### Risk Levels
* **SAFE:** Read-only diagnostics and non-destructive checks (automatic execution permitted).
* **MEDIUM:** Reversible state modifications (e.g., restarting an approved service or adapter). Requires confirmation and controlled elevation.
* **HIGH:** Destructive or security-sensitive actions (e.g., deleting user files, modifying registry, disabling Defender). **Strictly blocked from automatic execution.**

---

## 9. Administrator & UAC Elevation Strategy

1. **Un-elevated Default:** The Streamlit application runs un-elevated by default. SAFE tools execute without administrative privileges.
2. **Controlled Elevation for Repairs:** When a MEDIUM repair requires administrator rights, WinFix AI requests user confirmation and invokes a dedicated, controlled elevation helper.
3. **No Blanket Admin UI:** The Streamlit application must not simply run permanently as Administrator.

---

## 10. Repair Verification Contract

Every repair tool must specify an associated verification tool:

```text
Before State → Repair → After State → Verification → Confirmed Outcome
```

Outcomes are explicitly classified:
* **Fixed:** Problem resolved and confirmed by verification.
* **Not Fixed:** Verification indicates the problem persists.
* **Partially Fixed:** Some checks passed but issues remain.
* **Unable to Verify:** Verification could not complete.

---

## 11. Directory Structure

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

## 12. Canonical Implementation Roadmap

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

## 13. Installation & Getting Started

### 1. Prerequisites
* Windows 10 or 11
* Python 3.12 (preferred baseline)
* [Ollama](https://ollama.ai) installed locally
* Local model: `ollama pull gemma4:12b`

### 2. Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Launching WinFix AI
```powershell
streamlit run app.py
```

---

## 14. Non-Goals for MVP

* Cloud AI integration (strictly offline).
* Arbitrary command or PowerShell execution.
* Generic file deletion tools.
* Disabling antivirus or firewall protections.
* Driver uninstallation or registry cleaning utilities.
