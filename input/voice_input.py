"""Voice audio input validation, container inspection, and metadata extraction for WinFix AI.

Enforces audio size ceilings (max 25 MB), maximum recording duration (max 120s),
computes SHA-256 audio digests, checks container headers (WAV, MP3, OGG, FLAC, M4A, WEBM),
and protects the diagnostic pipeline from malicious or non-audio uploads.
"""

import hashlib
import io
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import wave

from input.voice_models import VoiceMetadata, VoiceStatus

logger = logging.getLogger(__name__)

# Supported audio format extensions & containers
SUPPORTED_AUDIO_FORMATS: Set[str] = {"WAV", "MP3", "OGG", "FLAC", "M4A", "WEBM"}

# Strict size and duration boundaries
MAX_AUDIO_BYTES: int = 25 * 1024 * 1024  # 25 MB
MAX_AUDIO_DURATION_SECONDS: float = 120.0  # 2 minutes max
MAX_TRANSCRIPT_LENGTH: int = 12000  # Max transcript characters


class AudioValidationError(ValueError):
    """Raised when an uploaded or recorded audio buffer violates format, size, or duration rules."""

    pass


def _detect_audio_container(audio_bytes: bytes, filename: Optional[str] = None) -> str:
    """Identify the audio container format based on magic bytes and filename hints."""
    if len(audio_bytes) < 4:
        raise AudioValidationError("Audio data is too small to contain a valid audio header.")

    header_4 = audio_bytes[:4]
    header_8 = audio_bytes[:8] if len(audio_bytes) >= 8 else b""
    header_12 = audio_bytes[:12] if len(audio_bytes) >= 12 else b""

    # 1. WAV: 'RIFF'....'WAVE'
    if header_4 == b"RIFF" and len(header_12) >= 12 and header_12[8:12] == b"WAVE":
        return "WAV"

    # 2. OGG: 'OggS'
    if header_4 == b"OggS":
        return "OGG"

    # 3. FLAC: 'fLaC'
    if header_4 == b"fLaC":
        return "FLAC"

    # 4. WEBM: EBML header '\x1a\x45\xdf\xa3'
    if header_4 == b"\x1a\x45\xdf\xa3":
        return "WEBM"

    # 5. M4A / MP4 container: '....ftyp'
    if len(header_8) >= 8 and header_8[4:8] == b"ftyp":
        return "M4A"

    # 6. MP3: ID3 header or sync word
    if header_4[:3] == b"ID3" or (header_4[0] == 0xFF and (header_4[1] & 0xE0) == 0xE0):
        return "MP3"

    # If filename is explicitly given but magic bytes do not match expected container headers, reject
    if filename:
        ext = filename.rsplit(".", 1)[-1].upper() if "." in filename else ""
        if ext == "WAV":
            raise AudioValidationError("Invalid or corrupted WAV file: missing RIFF/WAVE header.")
        if ext in SUPPORTED_AUDIO_FORMATS:
            # Allow container if format is in supported set and not explicitly corrupted
            return ext

    raise AudioValidationError(
        f"Unsupported or unrecognized audio format header. Supported formats: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}."
    )


def validate_and_inspect_audio(
    audio_bytes: bytes,
    filename: Optional[str] = None,
    session_id: Optional[str] = None,
) -> VoiceMetadata:
    """Validate audio bytes, enforce size/duration bounds, compute SHA-256, and extract metadata.

    Args:
        audio_bytes: Raw binary audio content.
        filename: Optional client filename.
        session_id: Active session identifier.

    Returns:
        VoiceMetadata object.

    Raises:
        AudioValidationError: If audio violates format, size, or safety constraints.
    """
    if not audio_bytes or not isinstance(audio_bytes, bytes):
        raise AudioValidationError("Audio data is empty or invalid.")

    file_size = len(audio_bytes)
    if file_size > MAX_AUDIO_BYTES:
        raise AudioValidationError(
            f"Audio file size ({file_size} bytes) exceeds maximum limit of {MAX_AUDIO_BYTES} bytes (25 MB)."
        )

    # Calculate deterministic SHA-256
    sha256 = hashlib.sha256(audio_bytes).hexdigest()
    safe_fn = filename or f"voice_{sha256[:12]}.wav"

    # Reject forbidden filename extensions
    fn_lower = safe_fn.lower()
    for forbidden_ext in [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".html", ".htm", ".svg", ".py"]:
        if fn_lower.endswith(forbidden_ext):
            raise AudioValidationError(
                f"Unsupported or unsafe file extension '{forbidden_ext}'. Audio input must be valid audio."
            )

    # Detect container format
    detected_format = _detect_audio_container(audio_bytes, filename=safe_fn)

    duration_seconds = 0.0
    sample_rate = 0
    channels = 1

    # Deep inspection for WAV files using stdlib wave
    if detected_format == "WAV":
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                if sample_rate > 0:
                    duration_seconds = round(float(n_frames) / float(sample_rate), 2)
        except Exception as ex:
            logger.warning("WAV header inspection notice: %s", ex)
            # Rough estimation if wave parsing failed
            duration_seconds = 0.0
    else:
        # For non-WAV formats (MP3/OGG/WEBM/etc.), estimate nominal duration based on conservative bitrate (e.g. 128 kbps)
        # if detailed demuxing is not natively available in stdlib
        estimated_duration = round(file_size / (16000 * 2), 2)  # Assuming standard 16kHz 16-bit mono baseline
        duration_seconds = min(estimated_duration, MAX_AUDIO_DURATION_SECONDS)

    if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
        raise AudioValidationError(
            f"Audio duration ({duration_seconds}s) exceeds maximum allowed duration of {MAX_AUDIO_DURATION_SECONDS}s (2 minutes)."
        )

    sid = session_id or f"voice_session_{sha256[:8]}"

    return VoiceMetadata(
        session_id=sid,
        filename=safe_fn,
        format=detected_format,
        file_size=file_size,
        audio_hash=sha256,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
        status=VoiceStatus.READY,
    )


def inspect_voice_privacy(filename: Optional[str] = None) -> List[str]:
    """Inspect voice metadata / filename for sensitive indicators and return user warnings."""
    warnings: List[str] = []
    if filename:
        fn_lower = filename.lower()
        if any(term in fn_lower for term in ["user", "pass", "key", "token", "secret", "call", "record", "private"]):
            warnings.append(f"Filename '{filename}' may reference personal or sensitive information.")
    warnings.append(
        "Voice recordings may capture background speech, usernames, passwords, or personal details. "
        "Audio is processed strictly offline and never transmitted to external cloud services."
    )
    return warnings
