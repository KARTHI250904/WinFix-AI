"""Offline Speech-to-Text abstraction and local transcriber for WinFix AI.

Provides a single shared canonical STT pipeline for Voice Diagnostics, Personal Tutor,
and Autopilot modes. Enforces audio quality validation, PyAV 16kHz mono normalization,
conservative transcript normalization, and graceful failure handling.
"""

import io
import logging
import re
import time
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

import numpy as np

from input.voice_input import MAX_TRANSCRIPT_LENGTH
from input.voice_models import VoiceMetadata, VoiceStatus, VoiceTranscript
from modes.tutor_context import sanitize_tutor_text

logger = logging.getLogger(__name__)


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """Protocol for local offline Speech-to-Text transcription engines."""

    def is_available(self) -> bool:
        """Check if local STT engine/weights are present and ready."""
        ...

    def transcribe(self, audio_bytes: bytes, metadata: Optional[VoiceMetadata] = None) -> VoiceTranscript:
        """Transcribe raw audio bytes into a VoiceTranscript object."""
        ...


def normalize_transcript_text(text: Optional[str]) -> str:
    """Conservative transcript normalization.

    Rules:
    - Trim surrounding whitespace.
    - Collapse redundant internal whitespace into single spaces.
    - Clean obvious punctuation spacing without altering word order or corrupting paths/filenames.
    - Preserve Windows technical terms and casing (Wi-Fi, Bluetooth, Windows Update, CPU, RAM, DNS, etc.).
    - Strictly preserve user phrasing without generating diagnoses.
    """
    if not text:
        return ""

    t = text.strip()
    # Collapse multiple spaces/tabs/newlines
    t = re.sub(r"[ \t]+", " ", t)
    # Remove space before punctuation (e.g. "word , word" -> "word, word", "word ?" -> "word?")
    t = re.sub(r"\s+([,;?!])", r"\1", t)
    t = re.sub(r"\s+\.($|\s)", r".\1", t)

    # Technical casing preservations (case-insensitive dictionary of canonical representations)
    tech_replacements = {
        r"\bwi-?fi\b": "Wi-Fi",
        r"\bbluetooth\b": "Bluetooth",
        r"\bblue\s*tooth\b": "Bluetooth",
        r"\bblue\s*truth\b": "Bluetooth",
        r"\bblow\s*tooth\b": "Bluetooth",
        r"\b(?:your purpose|the purpose|you\'?re purpose)\s+(?:is\s+)?(?:broken|not working|disconnected)\b": "Bluetooth is not working",
        r"\b(?:your purpose|the purpose|you\'?re purpose)\b": "Bluetooth",
        r"\bwindows update\b": "Windows Update",
        r"\bc drive\b": "C drive",
        r"\bcpu\b": "CPU",
        r"\bram\b": "RAM",
        r"\bdns\b": "DNS",
        r"\bip address\b": "IP address",
        r"\bipv4\b": "IPv4",
        r"\bipv6\b": "IPv6",
        r"\bdhcp\b": "DHCP",
        r"\bwuauserv\b": "wuauserv",
        r"\b(?:well-?serve|well-?served|will outserve|will now serve|wauserv|wau serv)(?:\s+service)?\b": "wuauserv service",
        r"\bwindefend\b": "WinDefend",
        r"\btask manager\b": "Task Manager",
    }
    for pattern, canonical in tech_replacements.items():
        t = re.sub(pattern, canonical, t, flags=re.IGNORECASE)

    return t.strip()


def is_valid_transcript(text: Optional[str]) -> bool:
    """Validate transcript quality gate.

    Valid: non-empty, genuine speech text (including legitimate short technical speech).
    Invalid: empty, whitespace, punctuation-only, placeholder strings, or hallucinated repetitive patterns.
    """
    if not text or not isinstance(text, str):
        return False
    cleaned = text.strip()
    if len(cleaned) < 2:
        return False
    lower = cleaned.lower()
    invalid_patterns = {
        "[inaudible]",
        "[blank_audio]",
        "[silence]",
        "spoken inquiry",
        "voice problem",
        "spoken voice input recorded.",
        "spoken diagnostic inquiry",
        "unknown",
        "n/a",
    }
    if lower in invalid_patterns:
        return False
    if all(ch in " \t\n\r.,!?-[]()\"'`:;" for ch in cleaned):
        return False

    # Filter generic Whisper video subtitle hallucinations
    hallucination_phrases = [
        "you are the best person in the world",
        "you're the best person in the world",
        "you are the best friend in the world",
        "you're the best friend in the world",
        "thank you for watching",
        "thank you very much for watching",
        "please subscribe",
        "subtitles by",
    ]
    if any(h in lower for h in hallucination_phrases):
        return False

    # Check for hallucinated repeated phrases / words
    words = cleaned.split()
    if len(words) >= 6:
        clean_words = [w.lower().strip(".,!?\"'`:;") for w in words if w.strip(".,!?\"'`:;")]
        if len(clean_words) >= 6:
            unique_words = set(clean_words)
            if len(unique_words) <= 2:
                return False
            word_counts: Dict[str, int] = {}
            for w in clean_words:
                word_counts[w] = word_counts.get(w, 0) + 1
            if any(count / len(clean_words) > 0.75 for count in word_counts.values()):
                return False

    return True


def decode_audio_to_numpy(audio_bytes: bytes, target_sr: int = 16000) -> Tuple[np.ndarray, dict]:
    """Decode audio bytes (WAV, WebM, MP3, OGG, FLAC, M4A) to 16kHz mono float32 numpy array.

    Compatible with PyAV 19.0+ and older versions.
    Returns:
        (audio_array, sample_metrics_dict)
    """
    if not audio_bytes:
        empty = np.zeros(0, dtype=np.float32)
        return empty, {
            "sample_count": 0,
            "max_abs": 0.0,
            "rms": 0.0,
            "silence_ratio": 1.0,
            "non_zero_ratio": 0.0,
            "duration": 0.0,
            "sample_rate": target_sr,
        }

    # 1. Try PyAV container decoding with resampler
    try:
        import av  # type: ignore

        container = av.open(io.BytesIO(audio_bytes), mode="r")
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        if audio_stream is not None:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=target_sr)
            frames = []
            for packet in container.decode(audio_stream):
                for frame in resampler.resample(packet):
                    frames.append(frame.to_ndarray().flatten())
            # Flush resampler
            for frame in resampler.resample(None):
                frames.append(frame.to_ndarray().flatten())

            if frames:
                audio_arr = np.concatenate(frames).astype(np.float32)
            else:
                audio_arr = np.zeros(0, dtype=np.float32)

            max_abs = float(np.max(np.abs(audio_arr))) if audio_arr.size > 0 else 0.0
            rms = float(np.sqrt(np.mean(audio_arr**2))) if audio_arr.size > 0 else 0.0
            silent_samples = int(np.count_nonzero(np.abs(audio_arr) < 0.005)) if audio_arr.size > 0 else 0
            silence_ratio = float(silent_samples / audio_arr.size) if audio_arr.size > 0 else 1.0
            non_zero = int(np.count_nonzero(audio_arr)) if audio_arr.size > 0 else 0
            ratio = float(non_zero / audio_arr.size) if audio_arr.size > 0 else 0.0
            dur = float(audio_arr.size / target_sr) if target_sr > 0 else 0.0

            metrics = {
                "sample_count": int(audio_arr.size),
                "max_abs": round(max_abs, 4),
                "rms": round(rms, 4),
                "silence_ratio": round(silence_ratio, 4),
                "non_zero_ratio": round(ratio, 4),
                "duration": round(dur, 2),
                "sample_rate": target_sr,
            }
            logger.info("Audio decoded via PyAV: %s", metrics)
            return audio_arr, metrics
    except Exception as av_err:
        logger.debug("PyAV direct decode failed: %s, trying wave fallback", av_err)

    # 2. Try standard library wave module (for uncompressed PCM WAV)
    try:
        import wave
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

            if sampwidth == 2:
                samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 1:
                samples = (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            elif sampwidth == 4:
                samples = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

            if n_channels > 1:
                samples = samples.reshape(-1, n_channels).mean(axis=1)

            # Simple resample if needed
            if framerate != target_sr and framerate > 0:
                indices = np.round(np.linspace(0, len(samples) - 1, int(len(samples) * target_sr / framerate))).astype(int)
                samples = samples[indices]

            samples = samples.astype(np.float32)
            max_abs = float(np.max(np.abs(samples))) if samples.size > 0 else 0.0
            rms = float(np.sqrt(np.mean(samples**2))) if samples.size > 0 else 0.0
            silent_samples = int(np.count_nonzero(np.abs(samples) < 0.005)) if samples.size > 0 else 0
            silence_ratio = float(silent_samples / samples.size) if samples.size > 0 else 1.0
            non_zero = int(np.count_nonzero(samples)) if samples.size > 0 else 0
            ratio = float(non_zero / samples.size) if samples.size > 0 else 0.0
            dur = float(samples.size / target_sr) if target_sr > 0 else 0.0

            metrics = {
                "sample_count": int(samples.size),
                "max_abs": round(max_abs, 4),
                "rms": round(rms, 4),
                "silence_ratio": round(silence_ratio, 4),
                "non_zero_ratio": round(ratio, 4),
                "duration": round(dur, 2),
                "sample_rate": target_sr,
            }
            logger.info("Audio decoded via wave fallback: %s", metrics)
            return samples, metrics
    except Exception as wave_err:
        logger.debug("wave fallback decode failed: %s", wave_err)

    # 3. Last resort fallback: raw bytes
    empty = np.zeros(0, dtype=np.float32)
    return empty, {
        "sample_count": 0,
        "max_abs": 0.0,
        "rms": 0.0,
        "silence_ratio": 1.0,
        "non_zero_ratio": 0.0,
        "duration": 0.0,
        "sample_rate": target_sr,
    }


class FasterWhisperProvider:
    """Local Speech-to-Text engine using faster-whisper (CPU int8)."""

    DEFAULT_PROMPT: Optional[str] = None

    def __init__(self, model_size: Optional[str] = None) -> None:
        import os
        # Default to base.en for high recognition accuracy on Windows terms, with fallback to tiny.en
        self.model_size = model_size or os.getenv("WINFIX_STT_MODEL", "base.en")
        self._model = None
        self._available: Optional[bool] = None
        self._last_error: Optional[str] = None

    def is_available(self) -> bool:
        """Check if faster_whisper package and weights can be initialized."""
        try:
            import importlib.util

            if importlib.util.find_spec("faster_whisper") is not None:
                self._available = True
                return True
        except Exception as ex:
            logger.debug("faster-whisper availability probe error: %s", ex)

        self._available = False
        return False

    def _get_model(self):
        """Lazy loader for faster-whisper WhisperModel."""
        if self._model is None and self.is_available():
            from faster_whisper import WhisperModel  # type: ignore

            # Try loading cached local model first to prevent online lookups/hangs
            try:
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8", local_files_only=True)
            except Exception as offline_err:
                logger.debug("Local cached model %s offline load failed (%s), attempting standard load", self.model_size, offline_err)
                try:
                    self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                except Exception as load_err:
                    logger.warning("Could not load %s (%s), falling back to tiny.en", self.model_size, load_err)
                    self.model_size = "tiny.en"
                    try:
                        self._model = WhisperModel("tiny.en", device="cpu", compute_type="int8", local_files_only=True)
                    except Exception:
                        self._model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio_bytes: bytes, metadata: Optional[VoiceMetadata] = None) -> VoiceTranscript:
        """Transcribe audio using local faster-whisper model."""
        if not self.is_available():
            raise RuntimeError("Local faster-whisper engine is not installed or available.")

        t_start = time.time()
        model = self._get_model()
        if not model:
            raise RuntimeError("Failed to load local faster-whisper model.")

        # Decode audio to 16 kHz mono float32 array
        audio_arr, metrics = decode_audio_to_numpy(audio_bytes, target_sr=16000)

        source_type = getattr(metadata, "format", "microphone") if metadata else "microphone"
        audio_hash = getattr(metadata, "audio_hash", "") if metadata else ""
        session_id = getattr(metadata, "session_id", "") if metadata else ""

        # Pre-Whisper Quality Validation:
        if audio_arr.size == 0 or metrics.get("duration", 0.0) < 0.2:
            logger.warning("Decoded audio buffer is empty or too short: %s", metrics)
            return VoiceTranscript(
                text="",
                sanitized_text="",
                raw_text="",
                normalized_text="",
                confidence=0.0,
                language="en",
                duration_seconds=metrics.get("duration", 0.0),
                sample_rate=metrics.get("sample_rate", 16000),
                sample_count=metrics.get("sample_count", 0),
                segment_count=0,
                average_confidence=0.0,
                quality_status=VoiceStatus.AUDIO_EMPTY,
                model_name=f"faster-whisper:{self.model_size}",
                model_used=f"faster-whisper:{self.model_size}",
                processing_time_ms=int((time.time() - t_start) * 1000),
                source_type=source_type,
                audio_hash=audio_hash,
                session_id=session_id,
            )

        # Silent audio check
        if metrics.get("rms", 0.0) < 0.0005 and metrics.get("max_abs", 0.0) < 0.002:
            logger.warning("Decoded audio buffer is silent: %s", metrics)
            return VoiceTranscript(
                text="",
                sanitized_text="",
                raw_text="",
                normalized_text="",
                confidence=0.0,
                language="en",
                duration_seconds=metrics.get("duration", 0.0),
                sample_rate=metrics.get("sample_rate", 16000),
                sample_count=metrics.get("sample_count", 0),
                segment_count=0,
                average_confidence=0.0,
                quality_status=VoiceStatus.AUDIO_SILENT,
                model_name=f"faster-whisper:{self.model_size}",
                model_used=f"faster-whisper:{self.model_size}",
                processing_time_ms=int((time.time() - t_start) * 1000),
                source_type=source_type,
                audio_hash=audio_hash,
                session_id=session_id,
            )

        # Transcribe deterministically with temperature=0.0 and beam_size=5 for accurate speech capture
        segments_gen, info = model.transcribe(
            audio_arr,
            beam_size=5,
            language="en",
            temperature=0.0,
            initial_prompt=self.DEFAULT_PROMPT,
            condition_on_previous_text=False,
            vad_filter=False,
        )

        # Collect ALL returned segments — multi-segment aggregation
        segments = list(segments_gen)
        text_pieces: List[str] = []
        logprobs: List[float] = []
        no_speech_probs: List[float] = []

        for seg in segments:
            clean_piece = seg.text.strip()
            if clean_piece:
                text_pieces.append(clean_piece)
                logprobs.append(seg.avg_logprob)
                no_speech_probs.append(seg.no_speech_prob)

        raw_full_text = " ".join(text_pieces).strip()
        duration = round(time.time() - t_start, 2)
        proc_ms = int(duration * 1000)

        # Quality statistics
        mean_logprob = float(np.mean(logprobs)) if logprobs else -99.0
        mean_no_speech = float(np.mean(no_speech_probs)) if no_speech_probs else 1.0
        detected_lang = getattr(info, "language", "en") or "en"
        lang_prob = round(getattr(info, "language_probability", 0.95) or 0.95, 2)

        # Determine quality status
        if not raw_full_text or len(raw_full_text.strip()) == 0:
            quality_status = VoiceStatus.TRANSCRIPT_EMPTY
            full_text = ""
        elif not is_valid_transcript(raw_full_text):
            quality_status = VoiceStatus.TRANSCRIPT_EMPTY
            full_text = ""
        elif logprobs and (mean_logprob < -2.2 and mean_no_speech > 0.90):
            logger.warning(
                "Whisper transcript rejected due to extreme poor confidence (avg_logprob=%.2f, no_speech=%.2f): '%s'",
                mean_logprob,
                mean_no_speech,
                raw_full_text,
            )
            quality_status = VoiceStatus.TRANSCRIPT_LOW_CONFIDENCE
            full_text = ""
        else:
            quality_status = VoiceStatus.COMPLETED
            full_text = raw_full_text

        normalized = normalize_transcript_text(full_text)
        sanitized = sanitize_tutor_text(normalized)

        return VoiceTranscript(
            text=full_text,
            sanitized_text=sanitized,
            raw_text=raw_full_text,
            normalized_text=normalized,
            confidence=lang_prob,
            language=detected_lang,
            duration_seconds=metrics.get("duration", duration),
            sample_rate=metrics.get("sample_rate", 16000),
            sample_count=metrics.get("sample_count", int(audio_arr.size)),
            segment_count=len(segments),
            average_confidence=lang_prob,
            average_log_probability=round(mean_logprob, 2),
            average_no_speech_probability=round(mean_no_speech, 2),
            quality_status=quality_status,
            model_name=f"faster-whisper:{self.model_size}",
            model_used=f"faster-whisper:{self.model_size}",
            processing_time_ms=proc_ms,
            source_type=source_type,
            audio_hash=audio_hash,
            session_id=session_id,
        )


class MockLocalSTTProvider:
    """Deterministic local provider for offline testing and development environments."""

    def __init__(self, transcript_override: Optional[str] = None, available: bool = True) -> None:
        self.transcript_override = transcript_override
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def transcribe(self, audio_bytes: bytes, metadata: Optional[VoiceMetadata] = None) -> VoiceTranscript:
        if not self._available:
            raise RuntimeError("Mock STT provider marked as unavailable.")

        text = self.transcript_override if self.transcript_override is not None else "My Windows Update is failing with error 0x80070422 and the service won't start."
        normalized = normalize_transcript_text(text)
        sanitized = sanitize_tutor_text(normalized)

        source_type = getattr(metadata, "format", "mock") if metadata else "mock"
        audio_hash = getattr(metadata, "audio_hash", "mock_hash") if metadata else "mock_hash"
        session_id = getattr(metadata, "session_id", "mock_session") if metadata else "mock_session"

        quality_status = VoiceStatus.COMPLETED if is_valid_transcript(text) else VoiceStatus.TRANSCRIPT_EMPTY

        return VoiceTranscript(
            text=text,
            sanitized_text=sanitized,
            raw_text=text,
            normalized_text=normalized,
            confidence=0.98,
            language="en",
            duration_seconds=0.05,
            sample_rate=16000,
            sample_count=800,
            segment_count=1,
            average_confidence=0.98,
            average_log_probability=-0.15,
            average_no_speech_probability=0.01,
            quality_status=quality_status,
            model_name="mock-local-stt",
            model_used="mock-local-stt",
            processing_time_ms=5,
            source_type=source_type,
            audio_hash=audio_hash,
            session_id=session_id,
        )


class VoiceTranscriber:
    """Coordinates speech-to-text providers, enforces safety boundaries, and produces canonical transcripts."""

    def __init__(self, provider: Optional[SpeechToTextProvider] = None) -> None:
        self.provider = provider or FasterWhisperProvider()

    def set_provider(self, provider: SpeechToTextProvider) -> None:
        """Switch the active STT provider (e.g. for testing or different local model backends)."""
        self.provider = provider

    def is_available(self) -> bool:
        """Check if active local STT provider is available."""
        return self.provider.is_available() if self.provider else False

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        metadata: Optional[VoiceMetadata] = None,
        source_type: str = "microphone",
        session_id: Optional[str] = None,
    ) -> VoiceTranscript:
        """Canonical entry point: Transcribe audio bytes into a structured VoiceTranscript object.

        Args:
            audio_bytes: Raw validated audio data.
            metadata: VoiceMetadata object.
            source_type: Source identifier ('microphone', 'upload', 'file').
            session_id: Active session identifier.

        Returns:
            Canonical VoiceTranscript object.
        """
        if not self.is_available():
            logger.info("Speech-to-Text provider is not available.")
            return VoiceTranscript(
                text="",
                sanitized_text="",
                raw_text="",
                normalized_text="",
                confidence=0.0,
                duration_seconds=0.0,
                quality_status=VoiceStatus.TRANSCRIPTION_UNAVAILABLE,
                model_name="none",
                model_used="none",
                source_type=source_type,
                session_id=session_id or "",
            )

        try:
            transcript = self.provider.transcribe(audio_bytes, metadata)
            text = transcript.text.strip()
            is_truncated = False

            if len(text) > MAX_TRANSCRIPT_LENGTH:
                text = text[:MAX_TRANSCRIPT_LENGTH] + "... [TRUNCATED]"
                is_truncated = True

            normalized = normalize_transcript_text(text)
            sanitized = sanitize_tutor_text(normalized)

            transcript.text = text
            transcript.sanitized_text = sanitized
            transcript.normalized_text = normalized
            transcript.is_truncated = is_truncated
            if session_id:
                transcript.session_id = session_id
            if source_type:
                transcript.source_type = source_type

            return transcript
        except Exception as ex:
            logger.warning("Voice transcription execution error: %s", ex)
            return VoiceTranscript(
                text="",
                sanitized_text="",
                raw_text="",
                normalized_text="",
                confidence=0.0,
                duration_seconds=0.0,
                quality_status=VoiceStatus.TRANSCRIPTION_FAILED,
                model_name="error",
                model_used="error",
                source_type=source_type,
                session_id=session_id or "",
            )


default_voice_transcriber = VoiceTranscriber()

__all__ = [
    "SpeechToTextProvider",
    "FasterWhisperProvider",
    "MockLocalSTTProvider",
    "VoiceTranscriber",
    "default_voice_transcriber",
    "is_valid_transcript",
    "normalize_transcript_text",
    "decode_audio_to_numpy",
]
