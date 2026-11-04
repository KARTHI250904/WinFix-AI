# WinFix AI — AI Quality & Diagnostic Evaluation Architecture

## 1. Overview & Objectives

**Phase 34 — AI Quality & Diagnostic Evaluation** establishes a deterministic, offline-first benchmarking and validation framework for WinFix AI's decision layer.

The evaluation framework verifies:
1. **Diagnostic Accuracy:** Does the system classify user symptoms into the correct Windows troubleshooting domain?
2. **Evidence Grounding:** Are diagnostic hypotheses grounded in observable system telemetry rather than fabricated assumptions?
3. **Contradiction Handling:** Does the system detect conflicting multi-source telemetry and re-evaluate rather than averaging contradictory signals?
4. **Tool Recommendation Quality:** Are proposed tools registered in the 59-tool allowlist? Are forbidden and unregistered tools rejected with a 0% error tolerance?
5. **Hallucination Resistance:** Does the engine avoid inventing system state, PIDs, IP addresses, or repair success claims without deterministic verification?
6. **Multimodal Consistency:** Do equivalent symptoms in text, screenshot, and voice transcript resolve to consistent domains and tool selections?
7. **Personal Tutor Quality:** Does the tutor mode explain diagnostic reasoning clearly without bypassing safety boundaries?
8. **Autopilot Safety:** Does Autopilot enforce the maximum 8-step ceiling and pause for user authorization on MEDIUM-risk actions?
9. **Offline Fallback:** Does the system degrade gracefully to deterministic heuristics when local LLM services are unavailable?

---

## 2. Core Invariants & Security Boundaries

The evaluation framework enforces non-negotiable safety rules:
- **`LLM != Windows Shell`**: The AI remains an advisor/planner; it cannot directly execute arbitrary commands.
- **`Diagnosis != Repair`**: Diagnostic conclusions do not authorize state-altering repair actions.
- **`Recommendation != Execution`**: Proposing a tool requires SafetyEngine authorization before execution.
- **`Execution != Success`**: Execution does not imply resolution; deterministic verification rules govern success.
- **`Tool Registry Invariant`**: ToolRegistry contains exactly **59 tools** (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates, 0 aliases).
- **`0 Prohibited AST Primitives`**: Zero calls to `subprocess`, `os.system`, `os.popen`, `eval`, or `exec`.

---

## 3. Evaluation Dataset Structure

The deterministic evaluation dataset (`agent/evaluation_dataset.py`) contains **55 scenarios** covering all 11 approved Windows domains:
1. `NETWORK` (DNS, adapter disconnects, DHCP/APIPA, high latency, upstream routing)
2. `PERFORMANCE` (CPU saturation, RAM exhaustion, disk bottleneck, rogue processes, normal baseline)
3. `STORAGE` (Low disk space, temporary file buildup, disk pressure, locked files)
4. `SERVICES` (Stopped service, running service, dependency failures, service crash)
5. `WINDOWS_UPDATE` (Update service stopped, error codes, update history, component store)
6. `WINDOWS_DEFENDER` (Stale signatures, real-time protection, threat status, service status)
7. `BLUETOOTH` (Service stopped, paired devices, radio disabled, adapter unavailable)
8. `APPLICATION_CRASH` (WER telemetry, crash logs, faulting module attribution, crash frequency)
9. `STARTUP` (High boot duration, post-boot CPU spikes, prolonged uptime)
10. `SYSTEM` (OS version query, RAM hardware topology, processor architecture, OEM motherboard info)
11. `UNKNOWN / ADVERSARIAL` (Ambiguous symptoms, prompt injection, fake tool rejection, unsupported domain)

---

## 4. Evaluation Engine Pipeline

```text
EvaluationScenario
       ↓
Domain Classification Check (Heuristic & AI)
       ↓
Evidence Grounding & Hypothesis Validation
       ↓
Tool Allowlist & Forbidden Tool Check (0% Tolerance)
       ↓
Contradiction & Conflict Assessment
       ↓
Adversarial & Hallucination Filter
       ↓
ScenarioEvaluationResult (PASS / FAIL / PARTIAL)
       ↓
EvaluationMetricsCalculator → EvaluationSummary
```
