# WinFix AI — Production Recovery Architecture (Phase 31)

## 1. Overview

Phase 31 establishes the **Production Reliability, Recovery & Resumable Troubleshooting** framework for WinFix AI. The system is designed to handle unplanned interruptions (process crashes, unexpected reboots, native API failures, network dropouts, and timeouts) safely and conservatively.

---

## 2. Core Safety Invariants

```
NEVER ASSUME A PREVIOUS REPAIR EXECUTED SUCCESSFULLY.
REVALIDATE CURRENT WINDOWS STATE BEFORE RESUMING.
REPAIR REPLAY IS STRICTLY PROHIBITED.
```

1. **Unknown Execution State:**
   If a workflow was interrupted during or immediately after a repair operation, the execution state is treated as ambiguous. WinFix AI does NOT automatically replay the repair tool.
2. **Authoritative State Revalidation:**
   Instead of re-executing mutations, the system triggers state revalidation using the allowlisted SAFE verification tool for that domain.
3. **Authorization Invalidation:**
   If post-interruption verification reveals the issue persists, the prior authorization token is invalidated. A new SHA-256 confirmation token and explicit user confirmation are required before another repair can proceed.
4. **Idempotency Engine:**
   Detects duplicate execution attempts, identifies argument mutations, enforces cross-session isolation, and prevents replay of unauthorized operations.

---

## 3. Recovery Lifecycle State Machine

```text
RUNNING -> CHECKPOINTED -> [INTERRUPTION] -> RECOVERING -> REVALIDATING -> RESUMABLE -> RESUMED
                                                       -> AUTHORIZATION_REQUIRED
                                                       -> CANCELLED / FAILED / UNRESOLVED
```

- `RUNNING`: Workflow actively executing diagnostic or repair steps.
- `CHECKPOINTED`: Sanitized state snapshot persisted at a safe lifecycle boundary.
- `INTERRUPTED`: Workflow execution interrupted before completion.
- `RECOVERING`: RecoveryManager loading and inspecting the latest session checkpoint.
- `REVALIDATING`: Verifying factual Windows state using domain verification tools.
- `RESUMABLE`: Telemetry verified; workflow can safely resume from the checkpointed step index.
- `AUTHORIZATION_REQUIRED`: Ambiguous state requires fresh user authorization.
- `COMPLETED`: Workflow successfully completed after verified resolution.

---

## 4. Checkpoint Strategy & Data Sanitization

Checkpoints are captured at key lifecycle transitions:
- Workflow initiated
- Diagnostic step completed
- Telemetry updated
- Hypothesis transition
- Before repair authorization
- After user confirmation
- After repair execution
- Before / after verification
- Workflow terminal states (Completed, Failed, Cancelled)

**Sanitization Policy:**
- No raw screenshots or pixel buffers
- No raw audio streams
- No plaintext tokens or secrets (redacted to `[REDACTED_FOR_SECURITY]`)
- No binary command payloads
- No arbitrary shell commands
