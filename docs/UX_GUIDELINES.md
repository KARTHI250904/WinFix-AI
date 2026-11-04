# WinFix AI — UX & Human Usability Guidelines (Phase 35)

## 1. Executive Summary & Core UX Principles
WinFix AI is built around a central user experience principle:
> **Make Windows troubleshooting understandable and reassuring to an ordinary person.**

The interface behaves like a calm, reliable, local Windows troubleshooting expert:
1. **Calm, Plain Language**: Avoid jargon (e.g. use *"Your internet connection is working, but Windows is having trouble finding websites"* instead of *"DNS resolution failure detected"*).
2. **Progressive Disclosure**: Deliver simple, actionable answers first, while keeping complete structured technical details available via expandable `"Technical details"` drawers.
3. **No Execution Without Approval**: Diagnoses and recommendations never execute automatic repairs without explicit user authorization for MEDIUM actions.
4. **Verification Grounding**: WinFix AI never declares a fix successful based only on execution completion; live post-repair verification determines resolution status.

---

## 2. User-Facing Terminology Mapping

| Engineering Term | User-Facing Plain Language | Explanation |
| :--- | :--- | :--- |
| **Diagnosis** | *What we found* | The human summary of the current PC condition |
| **Evidence** | *Why we think this* | Observed facts supporting the conclusion |
| **Hypothesis** | *Possible cause* | Plausible explanation separated from facts |
| **Tool** | *Windows check / action* | Allowlisted read-only query or verified action |
| **MEDIUM Risk** | *Requires your approval* | Explicit confirmation required prior to running |
| **SAFE Risk** | *Safe read-only check* | Read-only observation with zero modification |
| **Verification** | *Check whether the fix worked* | Deterministic post-repair state check |
| **Recovery** | *Safely continue* | Revalidating live state after interruption |
| **Telemetry** | *Technical diagnostics* | Local, privacy-preserving operational metrics |
| **Autopilot** | *Automated safe troubleshooting* | Bounded, verified multi-step plan with safety pauses |
| **Personal Tutor** | *Personal learning guide* | Educational explanations without executing repairs |

---

## 3. Standardized Diagnostic Result Presentation
Every diagnostic card is structured into five distinct sections:
```text
┌────────────────────────────────────────────────────────────┐
│ 🔍 What WinFix AI Found                                    │
│ Possible Cause: DNS Resolver Cache Corruption              │
│ Windows can connect to your network, but cannot find sites.│
│                                                            │
│ Confidence: High confidence                                │
│                                                            │
│ 📋 Why We Think This (Evidence) [Expanded]                 │
│ ✓ Network adapter is active (192.168.1.50)                 │
│ ✓ Default Gateway is reachable                             │
│ ⚠️ DNS lookup timed out                                    │
│                                                            │
│ ❓ What We Don't Know Yet (If Applicable)                  │
│ • Upstream router DNS cache status                         │
│                                                            │
│ 🛡️ Recommended Safe Next Steps                             │
│ • Flush DNS resolver cache                                 │
│                                                            │
│ 🛠 Technical Details (For Advanced Users) [Collapsed]      │
└────────────────────────────────────────────────────────────┘
```

### Deterministic Confidence Mapping
Confidence is calculated deterministically from verified evidence count and contradiction status:
- **High confidence**: $\ge 3$ verified evidence items, no contradictions, confirmed status.
- **Moderate confidence**: $1 - 2$ verified evidence items, no contradictions.
- **Low confidence**: Contradictions detected or explicit uncertainty present.
- **Not enough information**: Zero verified evidence items collected.

---

## 4. Standardized Repair Proposal & Confirmation Flow
For repair operations requiring user approval:
1. **Clear Action Description**: Plain language title and purpose.
2. **Safety Boundaries**: Explicitly state what will happen and what will **NOT** happen.
3. **Replay Protection**: Expired or previously executed tokens cannot be submitted again.
4. **Immediate Verification**: The card explicitly specifies the tool used to verify recovery.

---

## 5. Verification & Outcome Communication
Outcomes are categorized into three clear states:
- **Verified**: *"Fix verified — Windows is now in the expected healthy state."*
- **Partially Resolved**: *"The repair improved the situation, but the original problem is not fully resolved."*
- **Failed Verification**: *"The repair was attempted, but Windows is still not in the expected state. No additional repair was performed automatically."*

Before-and-after state comparisons are rendered in side-by-side structured panels.

---

## 6. Recovery UX
When an interrupted session is detected:
> *"We found an interrupted troubleshooting session. Before continuing, WinFix AI will check the current Windows state again."*

Adheres strictly to the Phase 31 safety rule: **Never assume a previous repair executed successfully; revalidate live state before continuing.**
