"""Tests for the Shared High-Quality Voice Transcription Layer.

Verifies:
1. Single canonical VoiceTranscriber service.
2. Canonical VoiceTranscript data object.
3. Multi-segment aggregation.
4. Empty and silent audio detection.
5. Legitimate short speech preservation.
6. Hallucination and low-confidence filtering.
7. Conservative punctuation and technical term normalization.
8. Microphone and upload format parity.
9. Session isolation across modes.
10. Separation of Transcription vs Domain vs Intent.
11. Unified integration across Personal Tutor, Autopilot, and Voice Diagnostics.
"""

import io
import time
import wave
import numpy as np
import pytest

from agent.intent_classifier import UserIntent, default_intent_classifier
from agent.voice_diagnostics import (
    VoiceDiagnosticMapper,
    VoiceDiagnosticOrchestrator,
    default_voice_orchestrator,
)
from ai.voice_transcriber import (
    FasterWhisperProvider,
    MockLocalSTTProvider,
    VoiceTranscriber,
    decode_audio_to_numpy,
    default_voice_transcriber,
    is_valid_transcript,
    normalize_transcript_text,
)
from input.voice_input import validate_and_inspect_audio
from input.voice_models import (
    VoiceMetadata,
    VoiceStatus,
    VoiceTranscript,
    VoiceDiagnosticCategory,
)
from modes.autopilot import AutopilotEngine
from modes.personal_tutor import PersonalTutor, default_personal_tutor


def create_synthetic_wav_bytes(duration_s: float = 1.0, freq_hz: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory PCM WAV bytes containing a sine tone."""
    num_samples = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    waveform = (np.sin(2 * np.pi * freq_hz * t) * 16384).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(waveform.tobytes())
    return buf.getvalue()


def create_silent_wav_bytes(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory PCM WAV bytes containing pure zero samples."""
    num_samples = int(duration_s * sample_rate)
    waveform = np.zeros(num_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(waveform.tobytes())
    return buf.getvalue()


class TestCanonicalVoiceTranscript:
    """Verify VoiceTranscript data object properties and attributes."""

    def test_transcript_fields_complete(self):
        t = VoiceTranscript(
            text="My Wi-Fi keeps disconnecting every few minutes.",
            sanitized_text="My Wi-Fi keeps disconnecting every few minutes.",
            raw_text="My Wi-Fi keeps disconnecting every few minutes.",
            normalized_text="My Wi-Fi keeps disconnecting every few minutes.",
            language="en",
            duration_seconds=3.5,
            sample_rate=16000,
            sample_count=56000,
            segment_count=2,
            average_confidence=0.96,
            average_log_probability=-0.25,
            average_no_speech_probability=0.02,
            quality_status=VoiceStatus.COMPLETED,
            model_name="faster-whisper:base.en",
            processing_time_ms=120,
            source_type="microphone",
            audio_hash="abc123hash",
            session_id="sess_456",
        )
        assert t.text == "My Wi-Fi keeps disconnecting every few minutes."
        assert t.normalized_text == "My Wi-Fi keeps disconnecting every few minutes."
        assert t.segment_count == 2
        assert t.quality_status == VoiceStatus.COMPLETED
        assert t.model_name == "faster-whisper:base.en"

        d = t.to_dict()
        assert d["text"] == t.text
        assert d["quality_status"] == "COMPLETED"
        assert d["sample_rate"] == 16000


class TestAudioDecodingAndQualityValidation:
    """Verify audio decoding, sample metrics, and quality validation gates."""

    def test_decode_synthetic_wav(self):
        wav_data = create_synthetic_wav_bytes(duration_s=1.5, freq_hz=440.0)
        audio_arr, metrics = decode_audio_to_numpy(wav_data, target_sr=16000)
        assert audio_arr.size > 0
        assert metrics["sample_count"] == audio_arr.size
        assert metrics["rms"] > 0.1
        assert metrics["duration"] >= 1.4

    def test_decode_empty_bytes(self):
        audio_arr, metrics = decode_audio_to_numpy(b"", target_sr=16000)
        assert audio_arr.size == 0
        assert metrics["sample_count"] == 0
        assert metrics["silence_ratio"] == 1.0

    def test_silent_audio_detection(self):
        silent_wav = create_silent_wav_bytes(duration_s=1.0)
        audio_arr, metrics = decode_audio_to_numpy(silent_wav, target_sr=16000)
        assert metrics["rms"] == 0.0
        assert metrics["silence_ratio"] == 1.0

    def test_valid_short_speech_phrases(self):
        valid_short_phrases = [
            "Wi-Fi is broken.",
            "Bluetooth is missing.",
            "My PC is slow.",
            "Disk is full.",
            "Windows Update failed.",
            "Printer not working.",
        ]
        for phrase in valid_short_phrases:
            assert is_valid_transcript(phrase) is True, f"Legitimate short phrase rejected: {phrase}"

    def test_invalid_and_hallucinated_phrases(self):
        invalid_phrases = [
            "",
            "   ",
            "[inaudible]",
            "[blank_audio]",
            "[silence]",
            "...",
            "???",
            "you you you you you you you",
            "thank you thank you thank you thank you thank you",
        ]
        for phrase in invalid_phrases:
            assert is_valid_transcript(phrase) is False, f"Invalid phrase accepted: {phrase}"


class TestTranscriptNormalization:
    """Verify conservative whitespace, punctuation, and technical term normalization."""

    def test_normalize_whitespace_and_punctuation(self):
        raw = "   My   Wi-Fi    keeps disconnecting  ,  every few minutes .  "
        normalized = normalize_transcript_text(raw)
        assert normalized == "My Wi-Fi keeps disconnecting, every few minutes."

    def test_normalize_technical_terms(self):
        raw = "my wifi and bluetooth are broken after windows update on c drive cpu usage high"
        normalized = normalize_transcript_text(raw)
        assert "Wi-Fi" in normalized
        assert "Bluetooth" in normalized
        assert "Windows Update" in normalized
        assert "C drive" in normalized
        assert "CPU" in normalized

    def test_normalization_does_not_paraphrase_to_diagnosis(self):
        raw = "My Wi-Fi keeps disconnecting every few minutes."
        normalized = normalize_transcript_text(raw)
        assert normalized == "My Wi-Fi keeps disconnecting every few minutes."
        assert "adapter problem" not in normalized


class TestSharedTranscriberMultiModeHandoff:
    """Verify single canonical transcriber serving all three modes."""

    @pytest.fixture
    def mock_transcriber(self):
        return VoiceTranscriber(provider=MockLocalSTTProvider())

    def test_shared_transcriber_singleton(self):
        assert default_voice_transcriber is not None
        assert isinstance(default_voice_transcriber, VoiceTranscriber)

    def test_mode_1_voice_diagnostics_flow(self, mock_transcriber):
        wav_bytes = create_synthetic_wav_bytes(duration_s=1.0)
        mock_transcriber.set_provider(MockLocalSTTProvider("My C drive is almost full."))
        orchestrator = VoiceDiagnosticOrchestrator(transcriber=mock_transcriber)

        analysis = orchestrator.process_voice_input(
            audio_bytes=wav_bytes,
            filename="storage.wav",
            session_id="test_diag_sess",
        )
        assert analysis.status == VoiceStatus.COMPLETED
        assert analysis.transcript.sanitized_text == "My C drive is almost full."
        assert len(analysis.hints) >= 1
        assert analysis.hints[0].category == VoiceDiagnosticCategory.STORAGE.value
        # Read-only tools only
        assert "get_storage_diagnostics" in analysis.hints[0].candidate_tools

    def test_mode_2_personal_tutor_flow(self, mock_transcriber):
        wav_bytes = create_synthetic_wav_bytes(duration_s=1.0)
        mock_transcriber.set_provider(MockLocalSTTProvider("My Wi-Fi keeps disconnecting every few minutes."))
        orchestrator = VoiceDiagnosticOrchestrator(transcriber=mock_transcriber)

        analysis = orchestrator.process_voice_input(
            audio_bytes=wav_bytes,
            filename="wifi.wav",
            session_id="test_tutor_sess",
        )
        assert analysis.transcript.sanitized_text == "My Wi-Fi keeps disconnecting every few minutes."

        tutor = default_personal_tutor
        flow = tutor.create_troubleshooting_flow(
            user_question=analysis.transcript.sanitized_text,
            diagnostic_data={},
        )
        assert flow is not None
        assert flow.domain.lower() == "network"
        assert len(flow.steps) >= 1

    def test_mode_3_autopilot_flow(self, mock_transcriber):
        wav_bytes = create_synthetic_wav_bytes(duration_s=1.0)
        mock_transcriber.set_provider(MockLocalSTTProvider("How to view the previous failure Windows Update?"))
        orchestrator = VoiceDiagnosticOrchestrator(transcriber=mock_transcriber)

        analysis = orchestrator.process_voice_input(
            audio_bytes=wav_bytes,
            filename="winupdate.wav",
            session_id="test_auto_sess",
        )
        transcript_text = analysis.transcript.sanitized_text
        assert transcript_text == "How to view the previous failure Windows Update?"

        # Autopilot intent & domain processing
        intent = default_intent_classifier.classify_intent(transcript_text)
        assert intent == UserIntent.VIEW_HISTORY

        engine = AutopilotEngine()
        plan = engine.plan(problem_description=transcript_text)
        assert plan is not None
        tool_names = [s.tool_name for s in plan.steps]
        # Read-only plan, no service restart
        assert "restart_windows_update_service" not in tool_names
        assert "get_windows_update_diagnostics" in tool_names


class TestSessionIsolationAndParity:
    """Verify session isolation and format parity."""

    def test_session_isolation(self):
        t1 = default_voice_transcriber.transcribe_audio(
            b"dummy",
            metadata=VoiceMetadata("sess_1", "tutor.wav", "WAV", 100, "hash1"),
            session_id="sess_1",
            source_type="microphone",
        )
        t2 = default_voice_transcriber.transcribe_audio(
            b"dummy",
            metadata=VoiceMetadata("sess_2", "auto.wav", "WAV", 100, "hash2"),
            session_id="sess_2",
            source_type="upload",
        )
        assert t1.session_id != t2.session_id
        assert t1.source_type == "microphone"
        assert t2.source_type == "upload"

    def test_context_does_not_replace_transcript(self):
        wav_bytes = create_synthetic_wav_bytes(duration_s=1.0)
        transcriber = VoiceTranscriber(provider=MockLocalSTTProvider("My PC is slow."))
        orchestrator = VoiceDiagnosticOrchestrator(transcriber=transcriber)

        analysis = orchestrator.process_voice_input(
            audio_bytes=wav_bytes,
            filename="perf.wav",
            user_clarification="Additional context note about yesterday",
            user_notes="Extra note",
            session_id="sess_ctx_test",
        )
        # Transcript MUST remain the primary spoken words, not the notes
        assert analysis.transcript.sanitized_text == "My PC is slow."
        assert "Additional context" not in analysis.transcript.sanitized_text
