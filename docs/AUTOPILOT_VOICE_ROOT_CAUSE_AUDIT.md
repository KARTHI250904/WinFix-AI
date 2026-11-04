# WINFIX AI — AUTOPILOT VOICE PATH ROOT CAUSE AUDIT
## Complete Runtime Call Chain, Parity Analysis & Root Cause Identification

**Date:** 2026-10-03  
**Status:** AUDITED & RESOLVED  
**Component:** Autopilot Mode Voice Handler (`app.py`), Voice Orchestrator (`agent/voice_diagnostics.py`), STT Provider (`ai/voice_transcriber.py`)

---

## 1. Exact Autopilot Button Handler & UI Code

In [`app.py`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/app.py#L1535-L1618), the Autopilot Voice transcription workflow is contained in `render_autopilot_mode()`:

- **Source File:** [`app.py`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/app.py)
- **Function:** `render_autopilot_mode(sys_info, diag_data, ollama_status)`
- **Line Numbers:** Lines 1535 – 1618
- **Audio Inputs Handled:**
  - `st.audio_input("Record voice problem directly:", key="auto_voice_mic_recorder")`
  - `st.file_uploader("Upload voice recording for Autopilot...", key="auto_voice_uploader")`
- **Button Key:** `btn_auto_voice_transcribe` (Line 1550)
- **Session State Keys Used:**
  - `st.session_state["auto_voice_mic_recorder"]`: Streamlit `UploadedFile` object from microphone
  - `st.session_state["auto_voice_uploader"]`: Streamlit `UploadedFile` object from file picker
  - `st.session_state["auto_voice_analysis"]`: Stores completed `VoiceAnalysis`
  - `st.session_state["auto_voice_fname"]`: Audio filename string
  - `st.session_state["active_autopilot_plan"]`: Bounded plan generated from transcript

---

## 2. Complete Runtime Call Chain

```
[Browser Microphone / File Uploader]
      ↓ (audio_bytes via auto_voice_file.getvalue())
[app.py : Line 1550 - btn_auto_voice_transcribe]
      ↓
[default_voice_orchestrator.process_voice_input() : agent/voice_diagnostics.py]
      ↓
[validate_and_inspect_audio() : input/voice_input.py]
      ↓ (Returns validated VoiceMetadata)
[default_voice_transcriber.transcribe_audio() : ai/voice_transcriber.py]
      ↓
[FasterWhisperProvider.transcribe() : ai/voice_transcriber.py]
      ↓
[decode_audio_to_numpy() : PyAV 16 kHz Mono float32 array extraction]
      ↓
[WhisperModel.transcribe(audio_arr, beam_size=5, initial_prompt=DEFAULT_PROMPT)]
      ↓ (Collects segment generator & computes logprob quality metrics)
[is_valid_transcript(transcript.text)]
      ↓
[VoiceDiagnosticMapper.map_transcript_to_hints()]
      ↓
[st.session_state["auto_voice_analysis"] = analysis]
      ↓
[st.rerun() → Renders "🎙️ What I heard" editable review card]
```

---

## 3. Comparison: Working Personal Tutor Path vs. Autopilot Path

| Pipeline Component | Personal Tutor Voice Path | Autopilot Voice Path | Parity Difference |
| :--- | :--- | :--- | :--- |
| **Audio Ingestion** | `st.audio_input` / `st.file_uploader` | `st.audio_input` / `st.file_uploader` | Identical |
| **Extraction** | `file.getvalue()` | `file.getvalue()` | Identical |
| **Validation Engine** | `validate_and_inspect_audio()` | `validate_and_inspect_audio()` | Identical |
| **Orchestrator** | `default_voice_orchestrator` | `default_voice_orchestrator` | Identical |
| **STT Provider** | `default_voice_transcriber` | `default_voice_transcriber` | Identical |
| **STT Backend** | `FasterWhisperProvider` (`base.en`) | `FasterWhisperProvider` (`base.en`) | Identical |
| **Audio Resampling** | PyAV 16 kHz mono float32 | PyAV 16 kHz mono float32 | Identical |
| **Domain Prompt** | `DEFAULT_PROMPT` | `DEFAULT_PROMPT` | Identical |
| **VAD Setting** | `vad_filter=False` | `vad_filter=False` | Identical |
| **Quality Gate** | `is_valid_transcript()` | `is_valid_transcript()` | Identical |
| **Session Key Target** | `tutor_voice_analysis` | `auto_voice_analysis` | Mode-isolated (Correct) |
| **UI Display Card** | `🎙️ What I heard` + edit box | `🎙️ What I heard` + edit box | Identical structure |

---

## 4. The Exact Failing Root Cause

During the audit of [`ai/voice_transcriber.py`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/ai/voice_transcriber.py), executing the transcription quality filter:

```python
# Quality filtering: Check for high-uncertainty / hallucinated noise
mean_logprob = float(np.mean(logprobs)) if logprobs else -99.0
mean_no_speech = float(np.mean(no_speech_probs)) if no_speech_probs else 1.0
```

threw:
```text
NameError: name 'np' is not defined
```

### Cascading Failure Mechanism
1. `numpy as np` was imported inside `decode_audio_to_numpy()` but was missing from the module-level imports at the top of `ai/voice_transcriber.py`.
2. When `FasterWhisperProvider.transcribe()` completed model execution and evaluated `mean_logprob = float(np.mean(logprobs))`, Python raised `NameError`.
3. `VoiceTranscriber.transcribe_audio()` caught the exception in its broad `except Exception` block and returned `VoiceTranscript(text="")`.
4. `is_valid_transcript("")` returned `False`.
5. `process_voice_input()` set `analysis.status = VoiceStatus.TRANSCRIPT_EMPTY`.
6. `app.py` in `render_autopilot_mode()` executed the fallback branch:
   ```python
   st.error("⚠️ Speech Not Understood: Your recording was received, but WinFix AI couldn't understand any spoken speech.")
   ```

---

## 5. End-to-End Real Audio Verification (Audited via `tests/audit_autopilot_voice_path.py`)

With `import numpy as np` added at module scope, all test cases pass with 100% parity:

### Test 1: Wi-Fi Disconnection (`2026-10-02T15-38_audio.wav`)
- **Sample Count:** 56,880 samples (3.56s at 16 kHz) | **RMS:** 0.0969
- **Direct Provider Transcript:** `"My Wi-Fi keeps disconnecting every few minutes."`
- **Autopilot Orchestrator Status:** `COMPLETED`
- **Autopilot Transcript:** `"My Wi-Fi keeps disconnecting every few minutes."`
- **Inferred Domain:** `NETWORK`
- **Candidate Read-Only Tools:** `check_internet_connectivity`, `get_network_adapters_diagnostics`, `get_dns_client_config`
- **UI Card Rendered:** `🎙️ What I heard` (Editable Text Area) $\rightarrow$ **PASS**

### Test 2: CPU Performance (`test_perf_audio.wav`)
- **Sample Count:** 69,440 samples (4.34s at 16 kHz) | **RMS:** 0.0978
- **Autopilot Orchestrator Status:** `COMPLETED`
- **Autopilot Transcript:** `"My computer is very slow and the CPU usage is very high."`
- **Inferred Domain:** `PERFORMANCE`
- **Candidate Read-Only Tools:** `get_cpu_diagnostics`, `get_memory_diagnostics`, `get_top_cpu_processes`
- **UI Card Rendered:** `🎙️ What I heard` (Editable Text Area) $\rightarrow$ **PASS**

### Test 3: Disk Storage (`test_storage_audio.wav`)
- **Sample Count:** 42,080 samples (2.63s at 16 kHz) | **RMS:** 0.1023
- **Autopilot Orchestrator Status:** `COMPLETED`
- **Autopilot Transcript:** `"My C drive is almost full."`
- **Inferred Domain:** `STORAGE`
- **Candidate Read-Only Tools:** `get_storage_diagnostics`, `get_temp_storage_info`
- **UI Card Rendered:** `🎙️ What I heard` (Editable Text Area) $\rightarrow$ **PASS**

---

## 6. Verification Classification

| Inspection Step | Method | Classification | Result |
| :--- | :--- | :--- | :--- |
| **Autopilot Button Handler Trace** | Source inspection of `render_autopilot_mode()` in `app.py` | **REAL** | VERIFIED |
| **Call Chain Audit** | `tests/audit_autopilot_voice_path.py` runtime step-through | **REAL** | VERIFIED |
| **Direct Provider vs. Orchestrator** | Comparative execution on identical WAV bytes | **REAL** | 100% PARITY |
| **Whisper Model & Execution** | `faster-whisper:base.en` on CPU `int8` | **REAL** | VERIFIED |
| **Domain & Tool Mapping** | `VoiceDiagnosticMapper` mapping to read-only tools | **REAL** | VERIFIED |
| **Automated Test Suite** | 79 pytest test cases covering voice diagnostics | **REAL** | PASS (79/79) |
