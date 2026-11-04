# WinFix AI — Resumable Troubleshooting Specification (Phase 31)

## 1. Scope & Resumption Rules

The `ResumeEngine` determines how an interrupted session proceeds based on its saved checkpoint and live environment state.

---

## 2. Decision Matrix

| Interrupted State | Checkpoint Age | Live Telemetry Condition | ResumeAction | Next Step / Action |
| :--- | :--- | :--- | :--- | :--- |
| `DIAGNOSING` | Fresh ($\le 1800$s) | Diagnostic in progress | `RESUME` | Continues diagnostic sequence from safe step index |
| `DIAGNOSING` | Stale ($> 1800$s) | Telemetry expired | `REVALIDATE` | Restarts initial diagnostic sequence with fresh telemetry |
| `REPAIRING` | Any | None / Incomplete | `REVALIDATE` | Runs domain verification tool (reauthorization required if unresolved) |
| `REPAIRING` / `VERIFYING` | Any | Telemetry proves `RESOLVED` | `RESUME` | Advances workflow step to terminal resolution without re-executing repair |
| `WAITING_FOR_CONFIRMATION` | Any | Pending user action | `AUTHORIZATION_REQUIRED` | Invalidate previous token and present new confirmation prompt |
| `RESOLVED` / `CANCELLED` | Any | Terminal state reached | `CANCEL` / `UNRESOLVED` | Workflow closed; no further execution allowed |

---

## 3. Replay Protection Scenarios

### Scenario 1: DNS Repair Crash
1. User confirms `flush_dns_cache`.
2. Application crashes mid-execution.
3. On restart, RecoveryManager loads checkpoint (`workflow_state="REPAIRING"`).
4. ResumeEngine identifies interrupted repair $\rightarrow$ blocks repair re-execution $\rightarrow$ executes `check_dns_resolution`.
5. If DNS works $\rightarrow$ Marks resolved.
6. If DNS still fails $\rightarrow$ Demands new user authorization (`AUTHORIZATION_REQUIRED`).

### Scenario 2: Service Restart Timeout
1. Service restart times out or Windows API returns transient error.
2. System records `EXECUTION_FAILED`.
3. RecoveryManager logs event `RECOVERY_FAILED` and maintains strict `MEDIUM repair retry = 0` limit.
4. User is informed via Personal Tutor / UI without looping.
