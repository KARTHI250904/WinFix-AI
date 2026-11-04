# WinFix AI — Autopilot Troubleshooting Workflow

## 1. Automated Troubleshooting Paradigm

Autopilot Mode provides structured, multi-step diagnostic and repair execution with minimal user interruption while preserving strict safety boundaries:

```
Understand → Diagnose → Present Plan → Request Authorization → Execute Bounded Actions → Verify → Adapt → Report
```

---

## 2. Autopilot Execution Lifecycle

```
                     User Problem Input (Text / Screenshot / Voice)
                                   │
                                   ▼
                     Problem Understanding & Goal Definition
                                   │
                                   ▼
             Plan Formulation (Max 5 Bounded Allowlisted Steps)
                                   │
                                   ▼
                 Cryptographic Plan Hash Authorization
                                   │
                                   ▼
                   Sequential Execution Loop (Step 1..N)
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
                 ▼                                   ▼
            SAFE Step                           MEDIUM Step
                 │                                   │
        Execute Read-Only                   Verify User Authorization Token
                 │                                   │
        Evaluate Preconditions              Execute Scoped Repair
                 │                                   │
                 │                          Execute Paired Verification Tool
                 │                                   │
                 │                        ┌──────────┴──────────┐
                 │                        │                     │
                 │                     VERIFIED           NOT VERIFIED
                 │                        │                     │
                 └────────────────────────┤                     ▼
                                          │            Mark VERIFICATION_FAILED
                                          │            Trigger Reassessment
                                          ▼
                               All Steps Completed
                                          │
                                          ▼
                               Final Summary Report
```

---

## 3. Core Autopilot Safety Constraints

1. **Strict Step Bounding**: Maximum of 5 steps per formulated plan.
2. **Fail-Closed on Unconfirmed Repairs**: An unconfirmed MEDIUM repair immediately blocks execution and prevents subsequent steps.
3. **No Dynamic Code / No Shell**: Every step references an allowlisted Python function in `ToolRegistry`.
4. **Mandatory Post-Repair Verification**: A step only receives status `VERIFIED` when its paired verification tool passes.

---

## 4. Verification Failure & Adaptive Reassessment

If a repair finishes with `verification_status="not_verified"`:
1. Autopilot marks the step as `VERIFICATION_FAILED`.
2. The overall plan transitions to `AutopilotStatus.VERIFICATION_FAILED`.
3. The system halts rather than blindly repeating the same repair.
4. The user is presented with the empirical findings and offered alternative diagnostic paths.
