# WinFix AI — Unified Multimodal Troubleshooting Workflow

## 1. Overview & Architectural Principle

WinFix AI enables non-technical Windows users to express computer issues through any combination of **Written Text**, **Visual Screenshots**, and **Spoken Voice Input**. 

Regardless of input mode, the system adheres to strict security, safety, and operational invariants:
- **Multimodal Input != Windows Command**: Visual OCR, voice transcripts, and user text never become shell commands.
- **Multimodal Input != Repair Authorization**: Evidence only suggests problem scope; repair tools always require explicit user authorization.
- **LLM != Windows Shell**: The local AI suggests hypotheses and explanations; execution occurs solely via strongly-typed allowlisted Python tools.
- **Diagnosis != Repair, Execution != Success**: Verification determines whether an issue is actually resolved.

---

## 2. Unified Multimodal Ingestion Pipeline

```
┌─────────────────┐   ┌───────────────────────┐   ┌─────────────────────┐
│  Written Text   │   │  Visual Screenshot    │   │  Spoken Audio (WAV) │
└────────┬────────┘   └──────────┬────────────┘   └──────────┬──────────┘
         │                       │                           │
         ▼                       ▼                           ▼
   Text Sanitizer        Ollama 'moondream'          'faster-whisper'
         │               (or Rule OCR Fallback)      (or Header Fallback)
         │                       │                           │
         └───────────────────────┼───────────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │     ProblemInput      │
                     │  - session_id         │
                     │  - text               │
                     │  - screenshot_ev      │
                     │  - voice_transcript   │
                     │  - user_context       │
                     └───────────┬───────────┘
                                 │
                                 ▼
                   ┌───────────────────────────┐
                   │ MultimodalEvidenceAdapter │
                   │  (Ingest into Evidence-   │
                   │   Store with Provenance)  │
                   └─────────────┬─────────────┘
                                 │
                                 ▼
                   ┌───────────────────────────┐
                   │    StructuredProblem      │
                   │  - domain                 │
                   │  - symptoms               │
                   │  - user_goal              │
                   │  - conflicting_evidence   │
                   └─────────────┬─────────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
   Personal Tutor Mode                         Autopilot Mode
 (Educational Step-by-Step)               (Bounded Multi-Step Plan)
```

---

## 3. Evidence Quality Tiers & Provenance

All observations are stored in the unified SQLite-backed `EvidenceStore` tagged by source and quality:

| Evidence Source | Quality Tier | Freshness TTL | Description |
| :--- | :--- | :--- | :--- |
| **`WINDOWS_TOOL`** | `VERIFIED` | 30s – 600s | Factual results from registered Windows diagnostic tools. Authoritative system state. |
| **`USER`** | `USER_REPORTED` | 300s | User prompts, symptom descriptions, and explicit context. |
| **`VOICE`** | `USER_REPORTED` | 300s | Transcribed speech from local STT engine. |
| **`SCREENSHOT`** | `INFERRED` | 300s | Visual observations, detected error dialogs, and OCR tokens. |
| **`KNOWLEDGE`** | `INFERRED` | 3600s | Knowledge base articles providing background educational context. |

---

## 4. Contradiction & Conflict Resolution

When user statements or visual inferences diverge from actual Windows diagnostics, WinFix AI avoids guessing and preserves evidence provenance:

```text
Evidence Priority:
VERIFIED Windows state  >  USER_REPORTED  >  INFERRED Visual Evidence
```

### Contradiction Handling Example:
- **User Statement**: "My Wi-Fi is disconnected."
- **Live Tool Diagnostics**: `get_network_adapters_diagnostics` reports 2 active adapters with valid IPv4 leases.
- **System Action**: Displays:
  > *"There is conflicting evidence: You reported that Wi-Fi is disconnected, but Windows detects 2 active network adapters. I will use the authoritative Windows state and proceed with an internet connectivity check."*

---

## 5. Offline-First Graceful Degradation

WinFix AI remains 100% functional even when offline or when optional local AI models are unavailable:

1. **Ollama Text LLM Offline**:
   - Switches transparently to deterministic domain strategies and knowledge base matching.
   - Message: *"Local AI is currently unavailable. WinFix AI can still perform verified Windows diagnostics and provide deterministic troubleshooting guidance."*
2. **Vision Model (`moondream`) Offline**:
   - Preserves screenshot file and falls back to user text context without guessing image contents.
   - Message: *"The screenshot was received successfully, but local visual analysis is currently unavailable. I will not guess what is visible in the screenshot. I can still use your written description and run verified Windows diagnostics."*
3. **STT Model (`faster-whisper`) Offline**:
   - Preserves audio metadata without inventing hallucinated text.
   - Message: *"Your audio was received successfully, but the local speech-to-text model is unavailable. I won't invent a transcript. You can type the problem instead."*
