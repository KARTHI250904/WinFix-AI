"""Input processing module for WinFix AI (text, screenshot, voice)."""

from input.screenshot_input import (
    MAX_HEIGHT,
    MAX_PIXELS,
    MAX_SCREENSHOT_BYTES,
    MAX_WIDTH,
    SUPPORTED_IMAGE_FORMATS,
    ScreenshotValidationError,
    inspect_privacy_indicators,
    validate_and_load_image,
)
from input.screenshot_models import (
    ScreenshotAnalysis,
    ScreenshotDiagnosticHint,
    ScreenshotEvidence,
    ScreenshotMetadata,
    ScreenshotObservation,
    ScreenshotObservationCategory,
)
from input.voice_input import (
    MAX_AUDIO_BYTES,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_TRANSCRIPT_LENGTH,
    SUPPORTED_AUDIO_FORMATS,
    AudioValidationError,
    inspect_voice_privacy,
    validate_and_inspect_audio,
)
from input.voice_models import (
    VoiceAnalysis,
    VoiceDiagnosticCategory,
    VoiceDiagnosticHint,
    VoiceMetadata,
    VoiceStatus,
    VoiceTranscript,
)

__all__ = [
    "MAX_HEIGHT",
    "MAX_PIXELS",
    "MAX_SCREENSHOT_BYTES",
    "MAX_WIDTH",
    "SUPPORTED_IMAGE_FORMATS",
    "ScreenshotAnalysis",
    "ScreenshotDiagnosticHint",
    "ScreenshotEvidence",
    "ScreenshotMetadata",
    "ScreenshotObservation",
    "ScreenshotObservationCategory",
    "ScreenshotValidationError",
    "inspect_privacy_indicators",
    "validate_and_load_image",
    "MAX_AUDIO_BYTES",
    "MAX_AUDIO_DURATION_SECONDS",
    "MAX_TRANSCRIPT_LENGTH",
    "SUPPORTED_AUDIO_FORMATS",
    "AudioValidationError",
    "inspect_voice_privacy",
    "validate_and_inspect_audio",
    "VoiceAnalysis",
    "VoiceDiagnosticCategory",
    "VoiceDiagnosticHint",
    "VoiceMetadata",
    "VoiceStatus",
    "VoiceTranscript",
]
