# WinFix AI — Autopilot Intent Understanding and Plan Selection Validation

## 1. Executive Summary

This document validates the resolution of the downstream Autopilot planning failure where non-repair queries (such as `"How to view the previous failure Windows Update?"`) previously resulted in unintended service restart / repair proposals (`restart_windows_update_service`).

The root cause was that Autopilot planning was coupled solely to the problem **DOMAIN** (`WINDOWS_UPDATE`) without discerning the user's specific **INTENT** (`VIEW_HISTORY`). The new architecture introduces a strict **Intent-First Planning Pipeline** separating Domain classification from Intent classification across all 9 WinFix AI domains.

---

## 2. Intent-First Planning Architecture

```
User Query / Voice Transcript
           │
           ├──────────────────────────────┬─────────────────────────────┐
           ▼                                                             ▼
   Domain Detection                                              Intent Classification
(e.g., WINDOWS_UPDATE, NETWORK,                               (e.g., VIEW_HISTORY, CHECK_STATUS,
 PERFORMANCE, STORAGE, etc.)                                  DIAGNOSE, EXPLAIN, REPAIR)
           │                                                             │
           └──────────────────────────────┬──────────────────────────────┘
                                          ▼
                         Intent-Constrained Autopilot Planner
                                          │
            ┌─────────────────────────────┴─────────────────────────────┐
            ▼                                                           ▼
    Read-Only Intents                                             Repair Intent
 (VIEW_HISTORY, CHECK_STATUS,                                      (REPAIR)
      DIAGNOSE, EXPLAIN)                                                │
            │                                               1. Diagnostics First
 1. Bounded Read-Only Tools (SAFE)                          2. Explicit Confirmation for MEDIUM
 2. Zero Service Restarts                                   3. Post-Repair Verification
 3. Zero Mutation Operations
 4. Zero Authorization Prompts
```

### Supported Intent Categories

| Intent | Description | Safety Guarantee | Example Queries |
| :--- | :--- | :--- | :--- |
| `VIEW_HISTORY` | Inspect historical failures, event logs, past crashes | **Read-only (SAFE)** — Zero repair / restart | *"How to view the previous failure Windows Update?"*, *"Show me my previous Wi-Fi problems"* |
| `CHECK_STATUS` | Check current service state, adapter info, resource usage | **Read-only (SAFE)** — Zero repair / restart | *"Is Windows Update running?"*, *"How do I see what is using my CPU?"* |
| `DIAGNOSE` | Root-cause analysis and problem symptom diagnosis | **Read-only (SAFE)** — Zero repair / restart | *"Why did my Windows Update fail?"*, *"My Wi-Fi keeps disconnecting"* |
| `EXPLAIN` | Educational inquiry and conceptual explanation | **Read-only (SAFE)** — Zero repair / restart | *"What is DNS cache?"*, *"Explain Windows Defender real-time protection"* |
| `REPAIR` | Explicit user request to fix, restart, reset, or clean | Diagnostic first, MEDIUM tools gated by authorization | *"Fix my Windows Update"*, *"Clean up temporary files on C drive"* |
| `CONFIGURE` | Explicit setting adjustments or feature toggle | Policy-bounded read-only inspection | *"Configure network adapter"*, *"Enable Bluetooth"* |

---

## 3. Real Observed Case Resolution

### User Voice Query:
> *"How to view the previous failure Windows Update?"*

### Previous (Incorrect) Behavior:
- Domain: `WINDOWS_UPDATE`
- Plan:
  1. `get_windows_update_health`
  2. `get_windows_update_diagnostics`
  3. `get_windows_update_service_status`
  4. `restart_windows_update_service` *(MEDIUM risk — Incorrectly prompted for authorization)*
  5. `get_windows_update_service_status`

### Current (Correct) Behavior:
- Domain: `WINDOWS_UPDATE`
- Intent: `VIEW_HISTORY`
- Plan Goal: *"Inspect Windows Update history, previous failure records, and error status."*
- Generated Plan Steps:
  1. `get_windows_update_diagnostics` (SAFE, read-only=True, req_confirm=False)
  2. `get_windows_update_health` (SAFE, read-only=True, req_confirm=False)
- **Result:** Purely read-only diagnostic plan. Zero service restarts. Zero MEDIUM repair operations. Zero unnecessary authorization prompts.

---

## 4. Multi-Domain Generalization Matrix

| Domain | Query Example | Detected Intent | Plan Strategy |
| :--- | :--- | :--- | :--- |
| **WINDOWS_UPDATE** | *"How to view the previous failure Windows Update?"* | `VIEW_HISTORY` | Read-only update history & health inspection |
| **WINDOWS_UPDATE** | *"Why did my Windows Update fail?"* | `DIAGNOSE` | Read-only update diagnostics, health, and service state |
| **WINDOWS_UPDATE** | *"Fix my Windows Update"* | `REPAIR` | Diagnostics $\rightarrow$ `restart_windows_update_service` (Auth required) $\rightarrow$ verify |
| **WINDOWS_UPDATE** | *"Is Windows Update running?"* | `CHECK_STATUS` | Read-only service status & health inspection |
| **NETWORK** | *"Show me my previous Wi-Fi problems"* | `VIEW_HISTORY` | Read-only adapter diagnostics & connection status |
| **NETWORK** | *"My Wi-Fi keeps disconnecting"* | `DIAGNOSE` | Read-only DNS check, connectivity check, adapter diagnostics |
| **NETWORK** | *"How do I see my Wi-Fi adapter information?"* | `CHECK_STATUS` | Read-only adapter diagnostics & DNS client config |
| **PERFORMANCE** | *"Why is my computer slow?"* | `DIAGNOSE` | Read-only CPU, RAM, and top process diagnostics |
| **PERFORMANCE** | *"How do I see what is using my CPU?"* | `CHECK_STATUS` | Read-only CPU diagnostics & top CPU process listing |
| **STORAGE** | *"How can I see what's taking space on C drive?"* | `CHECK_STATUS` | Read-only storage diagnostics & temp info |
| **STORAGE** | *"Clean up temporary files on C drive"* | `REPAIR` | Storage diagnostics $\rightarrow$ `clean_user_temp_cache` (Auth required) $\rightarrow$ verify |

---

## 5. Security and Safety Invariants

1. **Strict Intent Boundary Enforcement:** `AutopilotEngine.validate_and_build_plan()` explicitly checks `user_intent`. If `user_intent != UserIntent.REPAIR`, any step containing a mutating or `RiskLevel.MEDIUM` tool immediately raises a security rejection `ValueError`.
2. **LLM Prompt Hardening:** `AUTOPILOT_SYSTEM_INSTRUCTION` and `build_autopilot_prompt()` mandate intent constraints directly to the model, ensuring LLM planning reflects user intent.
3. **Loop & Replay Prevention:** Verified plan hashing with single-use authorization is preserved.
4. **SafetyEngine Untouched:** SafetyEngine continues to enforce administrative boundaries, confirmation gates, and tool allowlisting.

---

## 6. Test Suite and Verification Metrics

### Target Regression Suite (`tests/test_autopilot_intent_planning.py`):
- **18 / 18 PASSED (100%)**
  - `TestIntentClassifier`: 11 tests covering all intent categories and phrasing.
  - `TestAutopilotIntentPlanSelection`: 7 tests verifying exact plan steps, safety properties, and validation rejections.

### Comprehensive Cross-Mode Suite:
- **117 / 117 PASSED (100%)**
  - `tests/test_autopilot.py`
  - `tests/test_multimodal_autopilot.py`
  - `tests/test_voice_diagnostics.py`
  - `tests/test_voice_troubleshooting_workflow.py`

### Total Verified Tests: **135 / 135 PASSED**

---

## 7. Modified Files Summary

| File | Purpose of Modification |
| :--- | :--- |
| `agent/intent_classifier.py` | Added `UserIntent` enum and `UserIntentClassifier` for intent disambiguation. |
| `ai/autopilot_prompt.py` | Added intent & domain metadata into system instructions and prompt context. |
| `modes/autopilot.py` | Integrated intent classification into `plan()`, `_generate_deterministic_fallback_plan()`, and `validate_and_build_plan()`. |
| `agent/multimodal_adapter.py` | Wired intent awareness into `formulate_autopilot_plan()`. |
| `build/dist/WinFixAI/*` | Synchronized distribution bundle copies of all modified files. |
| `tests/test_autopilot_intent_planning.py` | Created comprehensive regression test suite. |
