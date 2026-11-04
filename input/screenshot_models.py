"""Data models for Screenshot Diagnostics in WinFix AI.

Provides typed structures for screenshot metadata, visible observations,
diagnostic hints, and complete screenshot analysis reports.
Follows offline-first and strict untrusted-data safety principles.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class ScreenshotAnalysisStatus(str, Enum):
    """Status states for screenshot vision analysis."""

    VISION_SUCCESS = "VISION_SUCCESS"
    VISION_REQUEST_TIMEOUT = "VISION_REQUEST_TIMEOUT"
    VISION_MODEL_MISSING = "VISION_MODEL_MISSING"
    VISION_MODEL_UNAVAILABLE = "VISION_MODEL_UNAVAILABLE"
    VISION_INVALID_RESPONSE = "VISION_INVALID_RESPONSE"
    VISION_REQUEST_ERROR = "VISION_REQUEST_ERROR"
    INVALID_IMAGE = "INVALID_IMAGE"
    UNSUPPORTED_IMAGE_FORMAT = "UNSUPPORTED_IMAGE_FORMAT"
    # Legacy alias
    SUCCESS = "VISION_SUCCESS"


class ScreenshotObservationCategory(str, Enum):
    """Categorization for visual elements extracted from a screenshot."""

    ERROR_MESSAGE = "ERROR_MESSAGE"
    WARNING = "WARNING"
    WINDOW_TITLE = "WINDOW_TITLE"
    APPLICATION_NAME = "APPLICATION_NAME"
    SERVICE_NAME = "SERVICE_NAME"
    ERROR_CODE = "ERROR_CODE"
    EVENT_ID = "EVENT_ID"
    BUTTON = "BUTTON"
    DIALOG = "DIALOG"
    STATUS = "STATUS"
    NETWORK_INFORMATION = "NETWORK_INFORMATION"
    STORAGE_INFORMATION = "STORAGE_INFORMATION"
    UPDATE_INFORMATION = "UPDATE_INFORMATION"
    SECURITY_INFORMATION = "SECURITY_INFORMATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class ScreenshotMetadata:
    """Metadata derived from validated screenshot image input."""

    filename: str
    format: str  # PNG, JPEG, WEBP
    width: int
    height: int
    file_size: int
    sha256: str
    aspect_ratio: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenshotObservation:
    """Individual visual observation extracted from screenshot."""

    category: str  # ScreenshotObservationCategory string
    text: str
    confidence: float = 1.0
    location: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenshotDiagnosticHint:
    """Candidate registered diagnostic tool mapped from visible evidence."""

    tool_name: str
    purpose: str
    risk_level: str  # SAFE, MEDIUM, HIGH
    evidence_reason: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenshotEvidence:
    """Structured collection of visual observations extracted from screenshot."""

    metadata: ScreenshotMetadata
    observations: List[ScreenshotObservation] = field(default_factory=list)
    raw_text_extracted: str = ""
    detected_error_codes: List[str] = field(default_factory=list)
    detected_event_ids: List[str] = field(default_factory=list)
    detected_applications: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "observations": [o.to_dict() for o in self.observations],
            "raw_text_extracted": self.raw_text_extracted,
            "detected_error_codes": self.detected_error_codes,
            "detected_event_ids": self.detected_event_ids,
            "detected_applications": self.detected_applications,
        }


@dataclass
class ScreenshotAnalysis:
    """Complete structured analysis of a screenshot, distinguishing facts from hypotheses."""

    evidence: ScreenshotEvidence
    visible_facts_summary: str
    possible_interpretations: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    diagnostic_hints: List[ScreenshotDiagnosticHint] = field(default_factory=list)
    recommended_next_step: str = "Run the suggested read-only diagnostic tools to verify current system state."
    privacy_warnings: List[str] = field(default_factory=list)
    analysis_duration_ms: int = 0
    model_used: str = ""
    status: str = ScreenshotAnalysisStatus.VISION_SUCCESS.value
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence": self.evidence.to_dict(),
            "visible_facts_summary": self.visible_facts_summary,
            "possible_interpretations": self.possible_interpretations,
            "uncertainties": self.uncertainties,
            "diagnostic_hints": [h.to_dict() for h in self.diagnostic_hints],
            "recommended_next_step": self.recommended_next_step,
            "privacy_warnings": self.privacy_warnings,
            "analysis_duration_ms": self.analysis_duration_ms,
            "model_used": self.model_used,
            "status": self.status,
            "created_at": self.created_at,
        }
