# WinFix AI — AI Decision & Diagnostic Intelligence (Phase 27)

## Overview

**WinFix AI** Phase 27 introduces the **AI Decision & Diagnostic Intelligence Engine**, establishing a structured pipeline for multi-modal evidence ingestion, normalization, contradiction detection, time-to-live freshness management, structured hypothesis generation, strict tool recommendation validation, and bounded deterministic diagnostic plans.

---

## 1. Non-Negotiable Security Invariants

Diagnostic Intelligence adheres strictly to the core safety architecture:

```text
LLM != Windows Shell
Diagnosis != Windows Command
Hypothesis != Windows Command
Evidence != Windows Command
Screenshot != Windows Command
Voice Transcript != Windows Command
Knowledge Article != Windows Command
Model Metadata != Windows Command
```

### Execution Boundary
```text
User Input / Multi-Modal Sensors
  ↓
Evidence Normalization & Provenance
  ↓
Contradiction & Freshness Checking
  ↓
AI Diagnostic Reasoning (Ollama / Fallback)
  ↓
Structured Diagnosis (Observations, Hypotheses, Uncertainty)
  ↓
ToolRegistry Allowlist Validation
  ↓
Deterministic Bounded Plan (Max 5 steps, 1 execution/tool)
  ↓
SafetyEngine Gate (SAFE auto-run / MEDIUM confirmation)
  ↓
Native Windows Tool Handler
  ↓
New Evidence Ingested & SQLite Audited
```

---

## 2. Evidence Architecture & Provenance

Implemented in `agent/evidence_models.py`:

* **`EvidenceType`**: `SYSTEM`, `NETWORK`, `PERFORMANCE`, `STORAGE`, `SERVICE`, `BLUETOOTH`, `WINDOWS_UPDATE`, `DEFENDER`, `APPLICATION_CRASH`, `SCREENSHOT`, `VOICE`, `KNOWLEDGE`, `USER_REPORTED`
* **`EvidenceQuality`**: `VERIFIED` (factual tool execution), `USER_REPORTED` (prompt/voice statement), `INFERRED` (screenshot/visual), `STALE` (expired beyond TTL), `CONFLICTING` (mutually exclusive observations), `UNKNOWN`
* **Domain Freshness TTLs**:
  - Network: 60 seconds
  - Performance: 30 seconds
  - Services / Bluetooth: 120 seconds
  - Storage / Defender / Screenshot / Voice / User: 300 seconds
  - System / Windows Update / Crash Logs: 600 seconds
  - Knowledge Base: 3600 seconds

---

## 3. Observation vs. Interpretation Separation

Every diagnosis cleanly separates four distinct cognitive tiers:
1. **OBSERVATION**: Factual raw system outputs and user statements.
2. **INTERPRETATION**: Logical implications derived from the observations.
3. **HYPOTHESIS**: Structured potential root causes with severity and supporting/contradicting evidence links.
4. **RECOMMENDATION**: Validated registered diagnostic tools.

---

## 4. Hypothesis Management & Status Rules

* **Hypothesis Statuses**: `POSSIBLE`, `SUPPORTED`, `CONTRADICTED`, `UNRESOLVED`, `VERIFIED`.
* **Prohibition of AI-Set VERIFIED Status**: The LLM is strictly prohibited from asserting `VERIFIED` on a hypothesis. Any attempt by LLM output to declare a hypothesis as verified is automatically demoted to `POSSIBLE` or `SUPPORTED`. True verification requires deterministic tool execution.

---

## 5. Bounded Diagnostic Plans & Loop Protection

* **Diagnostic Plan Limits**: Maximum **5 steps** per diagnostic plan.
* **Loop Protection**: Maximum **1 execution per unique tool** within a single plan to prevent recursive execution loops (`AI -> tool -> AI -> same tool`).
* **Tool Validation**: Recommended tools must match registered `SAFE` tools in `ToolRegistry`. Unapproved or dynamic commands are stripped immediately.

---

## 6. Offline Degraded Mode

When local Ollama is offline or model generation fails:
* Deterministic diagnostic rules match user inquiries across 8 diagnostic categories (Network, Storage, Performance, Service, Bluetooth, Update, Defender, Crash).
* Generates structured `DiagnosticResponse` with `is_degraded = True`.
* All 59 Windows diagnostic tools and SafetyEngine gates remain 100% operational.
