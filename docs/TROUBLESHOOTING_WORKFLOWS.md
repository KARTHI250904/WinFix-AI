# WinFix AI — Phase 28: Intelligent Troubleshooting Workflows & Guided Resolution

## 1. Overview & Architecture

Phase 28 establishes a deterministic, bounded, multi-step troubleshooting and resolution engine for WinFix AI. Building upon the Phase 27 Diagnostic Intelligence framework (hypotheses, multi-modal evidence store, and contradiction detection), Phase 28 coordinates the end-to-end resolution pipeline.

### Core Non-Negotiable Invariants:
1. `LLM != Windows Shell`: The AI reasoning model never generates or executes raw shell commands.
2. `Diagnosis != Repair Authorization`: A structured diagnosis or hypothesis does not grant permission to modify Windows system state.
3. `Repair Candidate != Repair Authorization`: Proposing a repair candidate is merely identifying an allowlisted tool; execution is strictly guarded.
4. `Repair Execution != Success`: Executing a repair tool never marks an issue resolved until verified post-execution.
5. `Deterministic Verification is Authoritative`: Resolution is determined solely by comparing factual before/after evidence from registered SAFE inspection tools.

---

## 2. Troubleshooting Workflow Architecture

```text
User Problem / Symptom
          │
          ▼
Multi-Modal Evidence Collection (Phase 27)
          │
          ▼
Diagnostic Intelligence Engine (Phase 27)
  ├── Observations
  ├── Interpretations
  └── Hypotheses
          │
          ▼
Troubleshooting Workflow Engine (Phase 28)
          │
          ├── Step 1: SAFE Diagnostic Telemetry
          ├── Step 2: Deterministic Precondition Checks
          ├── Step 3: Repair Candidate Generation & Validation
          │             │
          │             ▼
          │      [Risk Evaluation: SafetyEngine]
          │             │
          │             ▼
          │      [User Confirmation Boundary (MEDIUM Tools)]
          │             │
          │             ▼
          │      [Domain Repair Orchestrator (Phase 6–14)]
          │             │
          ├── Step 4: Deterministic Post-Repair Verification
          ├── Step 5: Before/After Evidence Comparison
          └── Step 6: Resolution Determination & Personal Tutor Context
```

---

## 3. Workflow State Machine & Bounded Execution

### State Transitions:
- `CREATED` ➔ `DIAGNOSING`, `VERIFY_PRECONDITION`, `CANCELLED`, `FAILED`, `UNRESOLVED`, `PAUSED`
- `DIAGNOSING` ➔ `VERIFY_PRECONDITION`, `WAITING_FOR_CONFIRMATION`, `UNRESOLVED`, `FAILED`, `CANCELLED`, `PAUSED`
- `VERIFY_PRECONDITION` ➔ `WAITING_FOR_CONFIRMATION`, `REPAIRING`, `FAILED`, `UNRESOLVED`, `CANCELLED`, `PAUSED`
- `WAITING_FOR_CONFIRMATION` ➔ `REPAIRING`, `CANCELLED`, `PAUSED`, `FAILED`
- `REPAIRING` ➔ `VERIFYING`, `FAILED`, `CANCELLED`
- `VERIFYING` ➔ `RESOLVED`, `PARTIALLY_RESOLVED`, `UNRESOLVED`, `DIAGNOSING`, `FAILED`, `CANCELLED`
- `PAUSED` ➔ `DIAGNOSING`, `VERIFY_PRECONDITION`, `WAITING_FOR_CONFIRMATION`, `CANCELLED`
- Terminal States: `RESOLVED`, `UNRESOLVED`, `PARTIALLY_RESOLVED`, `FAILED`, `CANCELLED`, `EXPIRED` (no outbound transitions)

### Strict Execution Bounds:
- **Maximum Workflow Steps**: Exactly 8 steps. Immutable limit cannot be expanded by AI.
- **Maximum Repair Executions**: Exactly 1 execution per repair tool per workflow.
- **Safe Diagnostic Retries**: Max 1 automatic retry for transient SAFE read-only failures.
- **MEDIUM Repair Retries**: Strictly 0 automatic retries. Fail-closed on error.

---

## 4. Precondition Validation & Repair Candidate Selection

Before any repair candidate can be offered for confirmation or execution:
1. **Registry Lookup**: Tool must exist in `ToolRegistry` with risk `<= MEDIUM`.
2. **Schema Validation**: All arguments are validated against predefined `ParameterSpec` types and bounds.
3. **Command Injection Prevention**: Metacharacters (`;`, `&&`, `|`, `` ` ``, `$`) in strings are blocked.
4. **Precondition Checks**:
   - Network tools: Verifies adapter presence.
   - Service tools: Verifies service name is alphanumeric allowlisted.
   - Cleanup tools: Blocks system32/critical OS paths.
5. **Deterministic Verification Method**: A valid registered SAFE verification tool must be bound.

---

## 5. Confirmation Binding & Session Isolation

Confirmation tokens are generated using SHA-256 cryptographic hashing bound strictly to:
$$\text{Token} = \text{SHA256}(\text{session\_id} : \text{workflow\_id} : \text{tool\_name} : \text{sorted\_arguments})[:16]$$

If session, workflow, tool, or arguments change, the token immediately becomes invalid. Replay across sessions or tools fails closed.

---

## 6. Deterministic Verification & Resolution Criteria

Resolution is evaluated by `DeterministicResolutionEngine` comparing `before_evidence` vs `after_evidence`:
- `RESOLVED`: Verification tool confirms transition from failed/unhealthy state to ok/healthy state.
- `NOT_RESOLVED`: Verification tool indicates persistent failure or unchanged error state.
- `PARTIALLY_RESOLVED`: Partial improvement in sub-components with remaining symptoms.
- `INCONCLUSIVE`: Verification telemetry is incomplete or missing.

---

## 7. Degraded Offline Mode & Personal Tutor Integration

- **Offline Mode**: If Ollama AI is offline or degraded, deterministic rule-based workflows remain 100% operational using cataloged heuristics.
- **Personal Tutor**: Provides educational walkthroughs explaining what was inspected, why each step was chosen, what Windows reported, and how resolution was verified.
