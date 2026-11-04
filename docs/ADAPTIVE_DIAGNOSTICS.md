# WinFix AI — Adaptive Diagnostic Intelligence (Phase 30)

## 1. Overview & Objectives

Phase 30 establishes a bounded, deterministic **Adaptive Diagnostic Intelligence** layer on top of Phases 27–29. Real-world Windows troubleshooting rarely follows a static, linear path because:
- User problem statements are often misleading, noisy, or symptom-only (e.g., "DNS is broken" when the DHCP lease expired).
- Evidence may be missing, stale, or contradictory.
- System state can evolve or change dynamically during the diagnostic workflow.

The Adaptive Diagnostic Engine ensures WinFix AI adapts its diagnostic direction dynamically without breaking deterministic safety bounds, authorizations, or workflow budgets.

---

## 2. Core Architecture

```
User Symptom
    ↓
Domain Classification (Phase 29)
    ↓
Initial Evidence Collection (Phase 27)
    ↓
Evidence Evolution & Contradiction Tracking (Phase 30)
    ↓
Adaptive Hypothesis Evaluation (Phase 30)
    ↓ (If contradicted)
Hypothesis Transition & Strategy Shift (Phase 30)
    ↓
Workflow Template & State Machine (Phase 28)
    ↓
SafetyEngine (Phase 2)
    ↓
SHA-256 User Confirmation (Phase 28)
    ↓
Allowlisted Tool Execution (Phase 0)
    ↓
Authoritative Verification Registry (Phase 29)
    ↓
Before / After Evidence Delta Comparison (Phase 30)
    ↓
Deterministic Resolution Analyzer (Phase 30)
```

---

## 3. Key Invariants & Safeguards

1. **Execution Success != Verification Success:**
   Successful exit code or tool completion never equals issue resolution. Only deterministic post-repair verification evaluated against the Verification Registry establishes resolution.
2. **Deterministic Adaptation:**
   Hypothesis transitions occur via programmatic telemetry evaluation (`is_contradictory`, `is_supporting`), not unconstrained LLM assertions.
3. **Workflow Budget Bound:**
   Adaptive reasoning is strictly bound by the $\le 8$ step workflow budget. If budget is exhausted, the workflow terminates fail-closed as `UNRESOLVED`.
4. **Retry Bounds:**
   - SAFE diagnostic retries: Maximum 1
   - MEDIUM repair retries: Strictly 0 (no automatic retries)
   - Repair loops: Strictly prohibited
5. **Cross-Session Isolation:**
   All adaptive contexts, evidence items, and hypothesis transitions are strictly bound to session UUIDs and isolated across sessions.

---

## 4. Adaptive Lifecycle States

```text
INITIAL -> COLLECTING -> EVALUATING -> [CONTRADICTED -> ADAPTING -> EVALUATING]
                                   -> AWAITING_AUTHORIZATION -> REPAIRING -> VERIFYING -> RESOLVED
                                                                                     -> UNRESOLVED / FAILED
```

- `INITIAL`: Session instantiated with initial symptom and classified domain.
- `COLLECTING`: Telemetry being gathered via allowlisted SAFE tools.
- `EVALUATING`: Testing telemetry against active hypothesis.
- `CONTRADICTED`: Factual evidence contradicts active hypothesis (e.g. DNS resolution works when DNS failure was suspected).
- `ADAPTING`: Transitioning to adapted hypothesis and re-selecting strategy.
- `AWAITING_AUTHORIZATION`: Proposing MEDIUM repair candidate with SHA-256 confirmation token.
- `REPAIRING`: Executing authorized repair tool.
- `VERIFYING`: Executing dedicated verification tool and analyzing before/after state diff.
- `RESOLVED` / `UNRESOLVED`: Final deterministic resolution outcome.
