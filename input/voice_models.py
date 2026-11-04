"""Data models and typed structures for Voice Input & Voice Diagnostics in WinFix AI.

Provides typed models for audio metadata, transcription results, diagnostic hints,
and complete voice analysis objects adhering strictly to offline-first safety rules.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class VoiceStatus(str, Enum):
    """Lifecycle and execution statuses for Voice input and processing."""

    READY = "READY"
    RECORDING = "RECORDING"
    TRANSCRIBING = "TRANSCRIBING"
    COMPLETED = "COMPLETED"
    AUDIO_INVALID = "AUDIO_INVALID"
    INVALID_AUDIO = "INVALID_AUDIO"  # Alias
    AUDIO_EMPTY = "AUDIO_EMPTY"
    EMPTY_AUDIO = "EMPTY_AUDIO"  # Alias
    AUDIO_SILENT = "AUDIO_SILENT"
    AUDIO_TOO_LARGE = "AUDIO_TOO_LARGE"
    AUDIO_TOO_LONG = "AUDIO_TOO_LONG"
    UNSUPPORTED_AUDIO_FORMAT = "UNSUPPORTED_AUDIO_FORMAT"
    TRANSCRIPTION_UNAVAILABLE = "TRANSCRIPTION_UNAVAILABLE"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    TRANSCRIPT_EMPTY = "TRANSCRIPT_EMPTY"
    TRANSCRIPT_LOW_CONFIDENCE = "TRANSCRIPT_LOW_CONFIDENCE"
    VOICE_ANALYSIS_FAILED = "VOICE_ANALYSIS_FAILED"
    CANCELLED = "CANCELLED"


class VoiceDiagnosticCategory(str, Enum):
    """Categorization for problem domains inferred from voice transcripts."""

    NETWORK = "NETWORK"
    STORAGE = "STORAGE"
    PERFORMANCE = "PERFORMANCE"
    SERVICE = "SERVICE"
    BLUETOOTH = "BLUETOOTH"
    WINDOWS_UPDATE = "WINDOWS_UPDATE"
    DEFENDER = "DEFENDER"
    APPLICATION_CRASH = "APPLICATION_CRASH"
    GENERAL = "GENERAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class VoiceMetadata:
    """Safe metadata derived from validated voice audio input."""

    session_id: str
    filename: str
    format: str  # WAV, MP3, OGG, FLAC, M4A, WEBM
    file_size: int
    audio_hash: str
    duration_seconds: float = 0.0
    sample_rate: int = 0
    channels: int = 1
    status: VoiceStatus = VoiceStatus.READY
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class VoiceTranscript:
    """Canonical structured transcription output produced by local Speech-to-Text provider."""

    text: str
    sanitized_text: str = ""
    raw_text: str = ""
    normalized_text: str = ""
    language: str = "en"
    duration_seconds: float = 0.0
    sample_rate: int = 16000
    sample_count: int = 0
    segment_count: int = 1
    average_confidence: float = 1.0
    average_log_probability: float = 0.0
    average_no_speech_probability: float = 0.0
    quality_status: VoiceStatus = VoiceStatus.COMPLETED
    model_name: str = "faster-whisper:base.en"
    processing_time_ms: int = 0
    source_type: str = "microphone"
    audio_hash: str = ""
    session_id: str = ""
    confidence: float = 1.0
    is_truncated: bool = False
    model_used: str = "faster-whisper:base.en"

    def __post_init__(self) -> None:
        if not self.sanitized_text:
            self.sanitized_text = self.text
        if not self.raw_text:
            self.raw_text = self.text
        if not self.normalized_text:
            self.normalized_text = self.sanitized_text or self.text
        if self.model_used == "none" and self.model_name != "none":
            self.model_used = self.model_name
        elif self.model_name == "none" and self.model_used != "none":
            self.model_name = self.model_used
        if self.average_confidence == 1.0 and self.confidence != 1.0:
            self.average_confidence = self.confidence
        elif self.confidence == 1.0 and self.average_confidence != 1.0:
            self.confidence = self.average_confidence

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if hasattr(self.quality_status, "value"):
            d["quality_status"] = self.quality_status.value
        return d


@dataclass
class VoiceDiagnosticHint:
    """Candidate registered read-only diagnostic tools mapped from voice transcript."""

    category: str  # VoiceDiagnosticCategory value
    confidence: float = 1.0
    candidate_tools: List[str] = field(default_factory=list)
    reason: str = ""
    tool_reasons: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VoiceAnalysis:
    """Complete structured diagnostic analysis of spoken voice input."""

    metadata: VoiceMetadata
    transcript: VoiceTranscript
    hints: List[VoiceDiagnosticHint] = field(default_factory=list)
    inferred_intent: str = ""
    what_needs_verification: List[str] = field(default_factory=list)
    recommended_next_steps: List[str] = field(default_factory=list)
    privacy_warnings: List[str] = field(default_factory=list)
    status: VoiceStatus = VoiceStatus.COMPLETED
    analysis_duration_ms: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "transcript": self.transcript.to_dict(),
            "hints": [h.to_dict() for h in self.hints],
            "inferred_intent": self.inferred_intent,
            "what_needs_verification": self.what_needs_verification,
            "recommended_next_steps": self.recommended_next_steps,
            "privacy_warnings": self.privacy_warnings,
            "status": self.status.value,
            "analysis_duration_ms": self.analysis_duration_ms,
            "created_at": self.created_at,
        }
