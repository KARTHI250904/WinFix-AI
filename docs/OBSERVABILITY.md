# WinFix AI — Observability & Telemetry Architecture (Phase 32)

## Overview

WinFix AI implements a production-grade, local-only, privacy-preserving observability architecture. It provides full visibility into diagnostic paths, evidence quality, workflow execution, repair lifecycle transitions, and recovery operations without transmitting telemetry over the network or exposing sensitive user data.

---

## Absolute Security & Privacy Invariants

```text
Telemetry is purely observational.
Telemetry cannot authorize repairs.
Telemetry cannot trigger or execute repairs.
Telemetry cannot modify verification results.
Telemetry cannot override recovery decisions.
```

### Privacy Guarantees
1. **Zero Secret Persistence**: Telemetry metadata is sanitized against allowlisted keys and regex patterns. Passwords, tokens, API keys, credentials, cookies, and raw authorization hashes are strictly stripped or redacted.
2. **Zero Raw Audio / Vision Storage**: Binary voice audio, spectrograms, and screenshot image bytes are stripped. Only sanitized classification outcomes and error codes are retained.
3. **No Command Strings**: Shell command lines (`powershell`, `cmd.exe`, `bash`) are stripped and neutralized.
4. **No Raw LLM Prompts or Responses**: Prompt strings and raw generation outputs are excluded to prevent leakage of user data.
5. **Bounded Metadata**: Metadata keys are capped at 25 per event, string values are truncated to 256 characters, and total serialized JSON size is bounded at 4 KB.

---

## Event Taxonomy

The system classifies telemetry events into structured lifecycles:

| Lifecycle | Event Types |
|---|---|
| **Session** | `SESSION_STARTED`, `SESSION_COMPLETED`, `SESSION_CANCELLED`, `SESSION_FAILED` |
| **Workflow** | `WORKFLOW_STARTED`, `WORKFLOW_STEP_STARTED`, `WORKFLOW_STEP_COMPLETED`, `WORKFLOW_COMPLETED`, `WORKFLOW_CANCELLED`, `WORKFLOW_TIMEOUT`, `WORKFLOW_UNRESOLVED` |
| **Diagnostic** | `DIAGNOSTIC_STARTED`, `DIAGNOSTIC_COMPLETED`, `HYPOTHESIS_CREATED`, `HYPOTHESIS_SUPPORTED`, `HYPOTHESIS_CONTRADICTED`, `HYPOTHESIS_REASSESSED`, `HYPOTHESIS_RESOLVED`, `HYPOTHESIS_UNRESOLVED` |
| **Evidence** | `EVIDENCE_COLLECTED`, `EVIDENCE_MUTATED`, `EVIDENCE_CONTRADICTED`, `EVIDENCE_STALE`, `EVIDENCE_EXPIRED` |
| **Repair** | `REPAIR_CANDIDATE_CREATED`, `REPAIR_AUTHORIZATION_REQUIRED`, `REPAIR_AUTHORIZED`, `REPAIR_AUTHORIZATION_REJECTED`, `REPAIR_EXECUTION_STARTED`, `REPAIR_EXECUTION_COMPLETED`, `REPAIR_EXECUTION_FAILED`, `REPAIR_VERIFICATION_STARTED`, `REPAIR_VERIFICATION_SUCCEEDED`, `REPAIR_VERIFICATION_FAILED`, `REPAIR_RESOLVED` |
| **Recovery** | `CHECKPOINT_CREATED`, `CHECKPOINT_RESTORED`, `CHECKPOINT_EXPIRED`, `CHECKPOINT_INVALIDATED`, `RECOVERY_STARTED`, `RECOVERY_STATE_REVALIDATED`, `RECOVERY_RESUMED`, `RECOVERY_CANCELLED`, `RECOVERY_FAILED`, `DUPLICATE_EXECUTION_BLOCKED`, `AUTHORIZATION_INVALIDATED`, `STALE_STATE_DETECTED` |
| **Dependency** | `MODEL_AVAILABLE`, `MODEL_UNAVAILABLE`, `MODEL_TIMEOUT`, `MODEL_ERROR`, `DEPENDENCY_AVAILABLE`, `DEPENDENCY_UNAVAILABLE` |

---

## Failure Taxonomy

Failures are categorized by deterministic application logic:
* `PRECONDITION_FAILED`
* `AUTHORIZATION_REQUIRED`
* `AUTHORIZATION_INVALID`
* `EXECUTION_FAILED`
* `VERIFICATION_FAILED`
* `TIMEOUT`
* `CANCELLED`
* `UNAVAILABLE`
* `CONFLICTING_EVIDENCE`
* `UNRESOLVED`
* `RECOVERY_FAILED`
* `STALE_STATE`
* `DUPLICATE_EXECUTION`
* `INVALID_INPUT`
* `VALIDATION_FAILED`
* `DEPENDENCY_UNAVAILABLE`
* `DATABASE_ERROR`
* `MODEL_UNAVAILABLE`

---

## Retention Policy

* **Age-based cleanup**: Historical events older than 30 days are pruned automatically.
* **Count-based ceiling**: Total telemetry events are capped at 50,000 records.
* **Active State Protection**: Sessions with active checkpoints in `workflow_checkpoints` are protected from pruning until resolution or expiration.
