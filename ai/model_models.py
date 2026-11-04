"""WinFix AI — AI Model Lifecycle Data Models (Phase 26).

Defines strongly-typed enumerations, records, and aggregate health structures
for local AI models (Text, Vision, STT).
Strictly adheres to: LLM != Windows Shell and Model Metadata != Windows Command.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelType(str, Enum):
    """Type/modality of the AI component."""

    TEXT = "TEXT"
    VISION = "VISION"
    STT = "STT"


class ModelStatus(str, Enum):
    """Lifecycle and operational status of an AI component."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class ModelCapability(str, Enum):
    """Specific capabilities supported by an AI model."""

    TEXT_GENERATION = "TEXT_GENERATION"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    VISION = "VISION"
    SPEECH_TO_TEXT = "SPEECH_TO_TEXT"


@dataclass(frozen=True)
class ModelInfo:
    """Strongly-typed, validated descriptor for a local AI model."""

    provider: str
    model_id: str
    model_type: ModelType
    installed: bool
    available: bool
    capabilities: List[ModelCapability] = field(default_factory=list)
    version: Optional[str] = None
    digest: Optional[str] = None
    size_bytes: Optional[int] = None
    status: ModelStatus = ModelStatus.UNKNOWN
    health: Optional[str] = None
    last_checked: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_operational(self) -> bool:
        """Return True if model is installed, available, and READY."""
        return self.installed and self.available and self.status == ModelStatus.READY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to sanitized dictionary representation."""
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "model_type": self.model_type.value,
            "installed": self.installed,
            "available": self.available,
            "capabilities": [c.value for c in self.capabilities],
            "version": self.version,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "status": self.status.value,
            "health": self.health,
            "last_checked": self.last_checked,
            "error": self.error,
        }


@dataclass(frozen=True)
class AIHealthAggregation:
    """Consolidated health report across all local AI subsystems."""

    ollama_status: ModelStatus
    text_ai_status: ModelStatus
    vision_ai_status: ModelStatus
    stt_status: ModelStatus
    overall_status: ModelStatus
    text_model_info: Optional[ModelInfo] = None
    vision_model_info: Optional[ModelInfo] = None
    stt_model_info: Optional[ModelInfo] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def is_fully_ready(self) -> bool:
        """Return True if all AI subsystems are operational."""
        return self.overall_status == ModelStatus.READY

    def is_degraded(self) -> bool:
        """Return True if core diagnostics can continue in degraded mode."""
        return self.overall_status in (ModelStatus.READY, ModelStatus.DEGRADED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert aggregation to structured dictionary."""
        return {
            "ollama_status": self.ollama_status.value,
            "text_ai_status": self.text_ai_status.value,
            "vision_ai_status": self.vision_ai_status.value,
            "stt_status": self.stt_status.value,
            "overall_status": self.overall_status.value,
            "text_model": self.text_model_info.to_dict() if self.text_model_info else None,
            "vision_model": self.vision_model_info.to_dict() if self.vision_model_info else None,
            "stt_model": self.stt_model_info.to_dict() if self.stt_model_info else None,
            "details": self.details,
            "timestamp": self.timestamp,
        }
