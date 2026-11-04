# WinFix AI — AI Model Management & Local AI Lifecycle (Phase 26)

## Overview

**WinFix AI** operates under a strict offline-first Windows architecture. AI components are treated as modular, optional enhancements rather than hard runtime requirements. Phase 26 establishes structured discovery, capability validation, configuration governance, health aggregation, safe switching, and degraded-mode resilience across all supported modalities:
* **Text Reasoning & Planning**: `gemma4:12b` (Ollama)
* **Visual Inspection & Screenshot Diagnostics**: `minicpm-v:latest` (Ollama)
* **Speech-to-Text & Voice Diagnostics**: `whisper_cpp` (Local offline engine)

---

## 1. Security Architecture & Invariants

Packaging and model management strictly adhere to non-negotiable security boundaries:

```text
LLM != Windows Shell
Voice Transcript != Windows Command
Knowledge != Windows Command
Screenshot != Windows Command
Model Metadata != Windows Command
Model Name != Windows Command
Model Configuration != Windows Command
```

### Prohibited Primitives & Execution Safeguards
* **0 AST prohibited execution calls**: No `subprocess`, `shell=True`, `os.system`, `os.popen`, `eval`, `exec`, `CreateProcess`, `WinExec`, or `ShellExecute`.
* **No Automatic/Silent Model Acquisition**: Startup, health evaluation, and runtime diagnostics NEVER execute `/api/pull`, download remote weights, or modify system files.
* **Non-LLM Authority**: Model configuration and registry cannot be altered by prompts, screenshots, voice input, knowledge articles, or LLM outputs. Model switching requires explicit UI/programmatic action with strict registry allowlist validation.

---

## 2. Model Data Model & Typing

Implemented in `ai/model_models.py`:

```python
class ModelType(str, Enum):
    TEXT = "TEXT"
    VISION = "VISION"
    STT = "STT"

class ModelStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

class ModelCapability(str, Enum):
    TEXT_GENERATION = "TEXT_GENERATION"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    VISION = "VISION"
    SPEECH_TO_TEXT = "SPEECH_TO_TEXT"
```

---

## 3. Controlled Model Registry

Defined in `ai/model_registry.py`:

| Modality | Approved Identifier | Provider | Capabilities | Default |
|---|---|---|---|---|
| **Text** | `gemma4:12b` | Ollama | `TEXT_GENERATION`, `STRUCTURED_OUTPUT` | **Yes** |
| **Text** | `gemma:7b` | Ollama | `TEXT_GENERATION`, `STRUCTURED_OUTPUT` | No |
| **Text** | `gemma:2b` | Ollama | `TEXT_GENERATION`, `STRUCTURED_OUTPUT` | No |
| **Text** | `llama3:8b` | Ollama | `TEXT_GENERATION`, `STRUCTURED_OUTPUT` | No |
| **Text** | `mistral:7b` | Ollama | `TEXT_GENERATION`, `STRUCTURED_OUTPUT` | No |
| **Vision** | `minicpm-v:latest` | Ollama | `TEXT_GENERATION`, `VISION` | **Yes** |
| **Vision** | `llava:latest` | Ollama | `TEXT_GENERATION`, `VISION` | No |
| **STT** | `whisper_cpp` | Local | `SPEECH_TO_TEXT` | **Yes** |
| **STT** | `faster-whisper` | Local | `SPEECH_TO_TEXT` | No |

---

## 4. Configuration Management & Model Switching

Managed by `AIConfigurationManager` in `ai/model_config.py`:
* **Path**: `%LOCALAPPDATA%\WinFixAI\Config\ai_models.json`
* **Validation**:
  - Rejects path traversal (`..`, `/`, `\`), command injection symbols (`&`, `;`, `|`, `` ` ``, `$`, `<`, `>`), and whitespace anomalies.
  - Rejects unapproved model IDs with fail-closed default fallback.
* **Model Switching Flow**:
  1. Validate requested ID against allowlisted registry for specified modality.
  2. Persist updated configuration to disk.
  3. Invalidate read-only generation caches (`ollama_client.clear_cache()`).
  4. Trigger fresh health evaluation.

---

## 5. Offline Resilience & Degraded Mode

When Ollama is offline or configured models are missing:
* **Diagnostic & Repair Assistant**: Uses built-in deterministic templates; all 59 Windows tools and SafetyEngine gates remain 100% operational.
* **Personal Tutor**: Generates structured, educational guidance using offline fallback explanations and local SQLite knowledge articles.
* **Screenshot Diagnostics**: Clearly informs user that Visual AI is unavailable without hallucinating or guessing.
* **Voice Diagnostics**: Informs user that Speech-to-Text is degraded.

---

## 6. Performance Monitoring & Metrics

Integrated with Phase 24 `default_profiler`:
* Tracks monotonic duration, memory RSS delta, and status for `model_discovery`, `validate_text_model`, `validate_vision_model`, `validate_stt_backend`, and `switch_model`.
* **Zero Telemetry / Absolute Privacy**: No prompts, audio streams, or screenshots are persisted or recorded.
