# WinFix AI — End-to-End Troubleshooting Architecture & User Experience

## 1. Executive Summary

WinFix AI delivers an offline-first, safety-governed Windows troubleshooting system for non-technical users. It operates across two primary interaction paradigms:
1. **Personal Tutor Mode**: Guided educational troubleshooting where each step is explained in plain English answering **WHY** a diagnostic is run, **WHAT** was found, **WHAT** the result means, and **What is the next step**.
2. **Autopilot Mode**: Bounded, multi-step orchestration (maximum 5 steps) where diagnostic evidence is gathered automatically, safe steps run directly, and medium-risk repairs require explicit cryptographic user authorization before execution and post-repair verification before claiming resolution.

Both paradigms accept three multimodal input modalities:
- **Written Description (Text)**: Free-form user symptoms mapped through domain classifiers.
- **Visual Screenshot (Vision)**: Screenshots analyzed locally (via `moondream:latest` or rule-based fallback).
- **Spoken Voice Input (Voice)**: Audio transcribed locally (via `faster-whisper` or rule-based fallback).

---

## 2. Core Security & Architectural Invariants

1. **LLM != Windows Shell**:
   - The LLM never executes shell scripts, arbitrary command lines, PowerShell cmdlets, or dynamic subprocesses.
   - All operations are executed strictly through registered, strongly-typed Python functions.
2. **Tool Registry Pinned at 59**:
   - 49 SAFE (read-only diagnostic) tools.
   - 10 MEDIUM (reversible, scoped repair) tools.
   - 0 HIGH risk tools.
   - 0 duplicated tools or unapproved aliases.
3. **Diagnosis != Authorization**:
   - Formulating a repair proposal or diagnosing a fault never automatically executes a repair.
   - MEDIUM risk repairs require explicit user confirmation bound cryptographically to session, tool name, and arguments.
4. **Execution != Success (Mandatory Post-Repair Verification)**:
   - Executing a repair never marks an issue as solved.
   - Every repair has a paired verification tool (e.g., `flush_dns_cache` -> `check_dns_resolution`).
   - If verification fails or is inconclusive, the system reports `VERIFICATION_FAILED` and triggers a reassessment without claiming resolution.

---

## 3. End-to-End Workflow Lifecycles

### 3.1 Personal Tutor Lifecycle
```
User Input (Text / Screenshot / Voice)
       │
       ▼
Domain Classification (9 domains: Network, Audio, Storage, Display, Performance, Update, Bluetooth, AppCrash, Defender)
       │
       ▼
Troubleshooting Flow Formulation (Ordered, domain-specific sequence of SAFE & MEDIUM tools)
       │
       ▼
Step Execution (WHY -> WHAT Found -> WHAT It Means -> What's Next)
       │
   ┌───┴────────────────────────────┐
   ▼                                ▼
SAFE Tool (Direct Execution)     MEDIUM Repair (Explicit Confirmation Modal)
   │                                │
   ▼                                ▼
Plain-English Interpretation     Post-Repair Verification Check
                                    │
                                    ▼
                             Adaptive Next Step / Flow Completion
```

### 3.2 Autopilot Lifecycle
```
User Input (Text / Screenshot / Voice)
       │
       ▼
Autopilot Plan Formulation (Bounded max 5 steps with preconditions, risks, verification requirements)
       │
       ▼
User Review & Cryptographic Authorization (Plan Hash Confirmation)
       │
       ▼
Sequential Step Execution Loop (SafetyEngine Gate)
       │
   ├── SAFE Step -> Execute & Evaluate Preconditions
   │
   └── MEDIUM Step -> Authorized Token Check -> Execute Repair -> Verification Tool Check
            │
            ├── Verification PASSED  -> Proceed to Next Step / Finish Plan
            └── Verification FAILED  -> Mark VERIFICATION_FAILED -> Reassess / Halt
```

---

## 4. Multimodal Fusion & Routing

| Input Modality | Primary Processing | Fallback Processing | Routing Target |
| :--- | :--- | :--- | :--- |
| **Written Text** | Ollama (`gemma4:12b`) | Deterministic Rule-Based Classifier | Personal Tutor / Autopilot |
| **Screenshot** | Ollama Vision (`moondream:latest`) | Rule-Based Error OCR/Pattern Matcher | 3-Way Action (Autopilot / Tutor / Assistant) |
| **Voice Audio** | `faster-whisper` (Local STT) | PyWave/WAV Header & Length Extractor | 3-Way Action (Autopilot / Tutor / Assistant) |

---

## 5. Subsystem Readiness Status

All 13 core subsystems have been verified operational on Windows 11:
- Application Directories (`READY`)
- SQLite Database with 25 tables (`READY`)
- Knowledge Base with 9 articles (`READY`)
- Tool Registry with 59 registered tools (`READY`)
- Safety Engine (`READY`)
- Local AI Model `gemma4:12b` (`READY`)
- Vision Analyzer `moondream:latest` (`READY`)
- Voice Transcriber `faster-whisper` (`READY`)
- Workflow & Resolution Engine (`READY`)
- Domain Intelligence & Strategies (`READY`)
- Adaptive Diagnostics & Scenario Engine (`READY`)
- Recovery & Resumption Engine (`READY`)
- Observability & Privacy-Preserving Telemetry (`READY`)
