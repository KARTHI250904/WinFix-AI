# WinFix AI — Product Requirements Document

## 1. Product Name

WinFix AI

## 2. Product Vision

WinFix AI is an offline-first, AI-powered Windows troubleshooting assistant designed to help both technical and non-technical users diagnose, understand, repair, and verify Windows computer problems safely.

The application uses a locally running Ollama model (`gemma4:12b`), ensuring that troubleshooting data and system telemetry never leave the user's computer.

The product operates in two user-selectable modes:
* **Personal Tutor:** For users who want to understand their system and learn what is happening step-by-step.
* **Autopilot:** For users who want safe, automated diagnosis and repairs with minimal interaction.

---

## 3. Primary Goals

1. **Offline-First:** Core AI reasoning, diagnostics, and persistence run entirely on the local machine.
2. **Local AI Model:** Powered by Ollama using `gemma4:12b` as the default configurable model.
3. **Python Baseline:** Built with Python (Python 3.12 preferred baseline for maximum library and OS API compatibility).
4. **Structured UI:** Clean, friendly Streamlit frontend with plain-English summaries by default.
5. **Local Persistence:** SQLite database storing sessions, diagnostics, repairs, feedback, and troubleshooting knowledge.
6. **Multi-Modal Input:** Supports natural language text, voice input (Phase 19), and error screenshots (Phase 18).
7. **Strict Safety Architecture:** `LLM != Windows Shell`. The LLM is a reasoning engine and never executes arbitrary commands.
8. **Controlled Tool Execution:** All Windows actions are explicit registered Python functions.
9. **Controlled Elevation Strategy:** SAFE tools run without elevation; MEDIUM tools prompt for user confirmation and elevate via controlled mechanisms; HIGH-risk actions are blocked.
10. **Mandatory Verification:** Every repair is paired with an automated verification check.

---

## 4. Target Users

### Primary User
A non-technical Windows user who experiences computer problems but does not know how to diagnose them, use command-line utilities, navigate PowerShell, or interpret system error codes.

### Secondary User
A technical user, system administrator, or developer who wants a fast, offline, and transparent troubleshooting assistant with access to structured technical diagnostics.

---

## 5. Core User Experience Flow

```text
User Problem (Text / Voice / Screenshot)
     ↓
Understand & Classify Problem
     ↓
Generate Diagnostic Plan
     ↓
Execute Safe Diagnostic Tools
     ↓
Collect & Analyze Evidence
     ↓
Identify Likely Root Cause
     ↓
Present Explanation & Recommended Fix
     ↓
Request User Approval & Elevation (if required)
     ↓
Execute Approved Repair Tool
     ↓
Execute Mandatory Verification Tool
     ↓
Report Confirmed Result (Fixed / Not Fixed / Partially Fixed / Unable to Verify)
```

---

## 6. Operating Modes

### 6.1 Personal Tutor Mode
* Explains technical concepts and diagnostic steps in plain, friendly language.
* Explains *why* a check is being performed and *what* the findings mean.
* Always requests explicit user permission before performing any repair action.
* Step-by-step guidance with expandable "Technical Details" for deeper inspection.

### 6.2 Autopilot Mode
* Autonomous troubleshooting flow designed for minimal user friction.
* Automatically creates diagnostic plans and executes approved SAFE diagnostic tools.
* Automatically executes approved SAFE repairs.
* Prompts the user for confirmation and elevation for MEDIUM-risk repairs.
* Strictly blocks HIGH-risk operations.
* Shows a real-time progress stepper and verifies all repairs.

---

## 7. Supported Troubleshooting Domains

1. **System Information:** Windows build, version, CPU, RAM, disk drives, uptime, architecture.
2. **Network Connectivity:** Wi-Fi, Ethernet, IP address, default gateway, DNS resolution/cache, network adapters.
3. **Computer Performance:** CPU, RAM, and Disk utilization; top resource-consuming processes; slow computer diagnostics.
4. **Storage:** Free disk space per volume, drive status, safe allowlisted temporary file and cache investigation.
5. **Windows Services:** Status, startup configuration, and controlled restart of allowlisted services.
6. **Bluetooth:** Adapter detection, Bluetooth service status, device visibility, safe troubleshooting.
7. **Printer:** Detection, print queue inspection, Print Spooler service state, controlled spooler restart, queue cleanup.
8. **Windows Update:** Service status, update error codes/history, connectivity checks, controlled service restart.
9. **Windows Defender:** Status, real-time protection, definition status (*read-only status reporting; never disabled*).
10. **Application Crashes:** Windows Error Reporting event log inspection, affected process diagnostics, safe recommendations.

---

## 8. Safety & Risk Classification

Every tool registered in WinFix AI must be assigned an explicit risk level:

* **SAFE:** Read-only diagnostics and strictly non-destructive inspections. Allowed to run automatically in Autopilot.
* **MEDIUM:** Operations modifying system configuration in a controlled, reversible manner (e.g., restarting an adapter, flushing DNS cache, restarting an allowlisted service). Requires user confirmation and controlled UAC elevation where administrative rights are necessary.
* **HIGH:** Destructive, risky, or security-lowering operations (e.g., deleting user documents, disabling Defender/Firewall, modifying arbitrary registry keys, uninstalling drivers). **Strictly blocked from automatic execution.**

---

## 9. Administrator & UAC Elevation Strategy

* **Un-elevated Baseline:** The Streamlit interface runs un-elevated. SAFE diagnostic tools run in user context.
* **Controlled Elevation:** When a repair tool requires elevation (`requires_admin = True`), WinFix AI presents a clear explanation to the user, requests confirmation, and invokes an isolated, controlled elevation helper.
* **No Blanket Admin App:** The application must not run permanently as Administrator by default.

---

## 10. Database Requirements

SQLite stores:
* `sessions`: Troubleshooting session metadata and timestamps.
* `problems`: Identified user problems and categories.
* `diagnostics`: Collected diagnostic evidence and tool outputs.
* `tool_executions`: Complete audit log of every tool execution.
* `solutions`: Proposed solutions, applied repairs, and verification outcomes.
* `feedback`: User satisfaction ratings and resolution confirmations.
* `settings`: Local application preferences and configuration overrides.

---

## 11. Canonical Implementation Phases

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

---

## 12. Non-Goals for MVP

* Cloud AI integration (strictly offline).
* Arbitrary PowerShell or command-line execution.
* Automatic registry cleaners or disk formatters.
* Automatic deletion of personal user files (Documents, Desktop, Downloads, Photos, Videos).
* Disabling antivirus, real-time protection, or firewall.
* Unsupervised driver installation/removal.
