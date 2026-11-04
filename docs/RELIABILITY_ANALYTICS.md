# WinFix AI — Reliability & Performance Analytics (Phase 32)

## Overview

The `TelemetryAnalytics` engine computes deterministic, descriptive statistics across all operational lifecycles. It does not perform subjective AI evaluations or ranking.

---

## Metric Suites

### 1. Workflow Summary & Duration Distribution
* **Total Workflows**: Aggregate count of initialized workflows.
* **Completion Distribution**: Counts and percentages of `COMPLETED`, `CANCELLED`, `TIMED_OUT`, and `UNRESOLVED` workflows.
* **Duration Statistics**: Mean, median, minimum, and maximum duration in milliseconds across completed workflows.

### 2. Diagnostic Intelligence & Evidence Quality
* **Hypothesis Evolution**: Count of hypotheses created, supported, contradicted, reassessed, and resolved.
* **Contradiction Rate**: Ratio of contradicted hypotheses to total created hypotheses ($\frac{\text{Contradicted}}{\text{Created}}$).
* **Reassessment Rate**: Frequency of diagnostic strategy updates in response to mutating evidence.
* **Evidence Volume**: Average items of authoritative telemetry gathered per diagnostic domain.

### 3. Distinct Repair Lifecycle Progression
WinFix AI tracks repair stages independently without collapsing execution into resolution:
```text
Candidates Created
       ↓
Authorizations Requested
       ↓
Authorizations Approved / Rejected
       ↓
Executions Started / Failed
       ↓
Verifications Started / Succeeded / Failed
       ↓
Resolved Repairs
```

### 4. Production Recovery & Replay Protection
* **Checkpoint Activity**: Counts of created, restored, expired, and invalidated checkpoints.
* **Recovery Resilience**: Frequency of successful resumptions vs. cancellations and failures.
* **Replay Protection**: Count of blocked duplicate repair executions across restart cycles.
* **Authorization Invalidation**: Count of stale authorization tokens neutralized on recovery.

### 5. Dependency & Subsystem Health
* **Local AI Model Availability**: Track uptime and response latencies for Ollama (`gemma4:12b`).
* **Vision & Voice Subsystems**: Record Pillow/Whisper library availability.
* **Windows Native APIs**: Monitor tool execution error rates across diagnostic domains.
