# WinFix AI — Shared Voice Transcription Architecture

## 1. Executive Summary

This architecture document defines the **Canonical Shared Voice Transcription Layer** for WinFix AI. This single, unified local pipeline powers voice input across all three primary WinFix AI modes:

1. **Voice Diagnostics** (Deterministic read-only diagnostic tool mapping)
2. **Personal Tutor** (Educational step-by-step problem explanation)
3. **Autopilot** (Bounded, verified, intent-first diagnostic and repair orchestration)

The architecture guarantees:
- **Offline Invariant:** 100% local transcription using `faster-whisper:base.en` (CPU, int8) and PyAV 16 kHz mono float32 audio normalization.
- **Single Canonical Service:** Exactly ONE shared transcriber (`default_voice_transcriber`) consumed by all three modes.
- **Strict Separation of Concerns:** Transcription is decoupled from Domain detection, which is decoupled from User Intent classification, which is decoupled from Mode execution.
- **Non-destructive Normalization:** Conservative whitespace and technical-casing normalization that never paraphrases user statements into diagnostic claims.
- **Quality & Hallucination Defense:** Rigorous pre-Whisper and post-Whisper quality gates preventing silent, empty, or hallucinated repetitive loops from polluting diagnostic workflows.

---

## 2. End-to-End Pipeline

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Audio Capture / Upload                        │
│          (Browser Microphone / Uploaded WAV, WebM, MP3, FLAC, OGG)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Audio Container Validation                      │
│        (File size ceiling: 25 MB | Max duration: 120s | SHA-256)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        PyAV In-Memory Decoding                         │
│               (Resample to 16 kHz Mono Float32 NumPy Array)            │
│         (Calculate Sample Count, Duration, Max Abs, RMS, Silence)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Pre-Whisper Quality Gate                         │
│       (Reject empty/short <0.2s or silent RMS <0.0005 recordings)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     faster-whisper:base.en (CPU int8)                  │
│       (Beam search: 5 | Domain-conditioned Technical Prompt)           │
│       (Multi-segment aggregation: collect ALL segments + logprobs)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Post-Whisper Quality Gate                         │
│          (Filter low log-prob / no-speech / repetitive loops)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Conservative Normalization                         │
│         (Trim whitespace, normalize punctuation, preserve terms)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Canonical VoiceTranscript Object                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ Voice Diagnostics│      │  Personal Tutor  │      │    Autopilot     │
│  Mode Workflow   │      │  Mode Workflow   │      │  Mode Workflow   │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

---

## 3. Canonical VoiceTranscript Object Schema

The unified `VoiceTranscript` object is defined in [`input/voice_models.py`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/input/voice_models.py):

| Field | Type | Description |
| :--- | :--- | :--- |
| `text` | `str` | Recognized transcribed text. |
| `raw_text` | `str` | Unmodified multi-segment raw Whisper output. |
| `normalized_text` | `str` | Normalized text with preserved Windows technical terms. |
| `sanitized_text` | `str` | Privacy-masked and prompt-injection-safe text. |
| `language` | `str` | Detected language code (`"en"`). |
| `duration_seconds` | `float` | Audio recording duration in seconds. |
| `sample_rate` | `int` | Sample rate baseline (`16000` Hz). |
| `sample_count` | `int` | Number of audio samples processed. |
| `segment_count` | `int` | Number of segments returned by Whisper. |
| `average_confidence` | `float` | Language probability / recognition confidence (0.0 to 1.0). |
| `average_log_probability` | `float` | Mean segment log probability. |
| `average_no_speech_probability` | `float` | Mean segment no-speech probability. |
| `quality_status` | `VoiceStatus` | Status flag (`COMPLETED`, `AUDIO_SILENT`, `TRANSCRIPT_EMPTY`, `TRANSCRIPT_LOW_CONFIDENCE`). |
| `model_name` | `str` | Underlying model identifier (`"faster-whisper:base.en"`). |
| `processing_time_ms` | `int` | Total end-to-end transcription latency in milliseconds. |
| `source_type` | `str` | Input origin (`"microphone"` or `"upload"`). |
| `audio_hash` | `str` | SHA-256 digest of input audio bytes. |
| `session_id` | `str` | Session identifier bound to the active mode. |

---

## 4. Multi-Segment Aggregation and Quality Protection

- **Segment Concatenation:** Whisper may emit multiple distinct time-coded segments for natural sentences. All segments are aggregated in sequence (`full_text = " ".join(text_pieces).strip()`) to ensure zero dropped clauses.
- **Short Speech Preservation:** Legitimate short phrases (e.g., *"Wi-Fi is broken."*, *"Bluetooth is missing."*, *"My PC is slow."*, *"Disk is full."*, *"Windows Update failed."*, *"Printer not working."*) are explicitly preserved and validated.
- **Hallucination Defense:** If repetitive phrase loops (e.g. repeated words making up $>75\%$ of words or vocabulary size $\le 2$ on 6+ words) are detected, the transcript is rejected with `VoiceStatus.TRANSCRIPT_EMPTY`.

---

## 5. Mode Handoff and Security Invariants

1. **Voice Diagnostics:** Transcribed text passes to `VoiceDiagnosticMapper` to suggest approved, read-only diagnostic tools. Mutating repairs are strictly excluded.
2. **Personal Tutor:** Transcribed text passes to `PersonalTutor.create_troubleshooting_flow()` to synthesize structured explanations (`WHY`, `WHAT WAS FOUND`, `WHAT IT MEANS`, `WHAT TO DO NEXT`).
3. **Autopilot:** Transcribed text passes to `UserIntentClassifier` and `AutopilotEngine.plan()`. Read-only intents (`VIEW_HISTORY`, `CHECK_STATUS`, `DIAGNOSE`, `EXPLAIN`) strictly produce read-only plans; `REPAIR` intent requires diagnosis first and explicit user confirmation for MEDIUM-risk tools.
4. **LLM != Windows Shell:** Voice transcripts are strictly passive untrusted data and can never execute arbitrary commands or bypass SafetyEngine.
