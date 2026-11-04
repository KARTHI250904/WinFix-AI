"""Comprehensive audit of Autopilot Voice Transcription Path vs Direct Provider."""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.voice_diagnostics import default_voice_orchestrator
from ai.voice_transcriber import FasterWhisperProvider, decode_audio_to_numpy, is_valid_transcript, default_voice_transcriber
from input.voice_input import validate_and_inspect_audio
from input.voice_models import VoiceStatus, VoiceMetadata

TEST_FILES = [
    ("2026-10-02T15-38_audio.wav", "My Wi-Fi keeps disconnecting every few minutes."),
    ("test_perf_audio.wav", "My computer is very slow and the CPU usage is very high."),
    ("test_storage_audio.wav", "My C drive is almost full."),
]

def audit_autopilot_voice_path():
    print("=" * 75)
    print("WINFIX AI — AUTOPILOT VOICE PATH RUNTIME AUDIT")
    print("=" * 75)

    for file_path, expected_text in TEST_FILES:
        if not os.path.exists(file_path):
            print(f"Skipping missing file: {file_path}")
            continue

        raw_bytes = open(file_path, "rb").read()
        file_size = len(raw_bytes)
        print(f"\n[AUDIT TEST FILE]: {file_path} ({file_size:,} bytes)")
        print("-" * 75)

        # 1. Validation step (as performed in process_voice_input)
        metadata = validate_and_inspect_audio(raw_bytes, filename=file_path, session_id="audit_auto_sess")
        print(f"1. Validation Metadata:")
        print(f"   - Format: {metadata.format} | Size: {metadata.file_size} | Hash: {metadata.audio_hash}")
        print(f"   - Channels: {metadata.channels} | Sample Rate: {metadata.sample_rate} | Duration: {metadata.duration_seconds:.2f}s")
        print(f"   - Status: {metadata.status.value}")

        # 2. PyAV Decoding (as performed inside FasterWhisperProvider)
        audio_arr, pcm_metrics = decode_audio_to_numpy(raw_bytes, target_sr=16000)
        print(f"\n2. Decoded PCM Audio Metrics:")
        print(f"   - Sample Count: {pcm_metrics['sample_count']:,}")
        print(f"   - Duration: {pcm_metrics['duration']:.2f}s")
        print(f"   - dtype: {audio_arr.dtype} | shape: {audio_arr.shape}")
        print(f"   - Max Amplitude: {pcm_metrics['max_abs']:.4f} | RMS: {pcm_metrics['rms']:.4f}")
        print(f"   - Non-zero ratio: {pcm_metrics['non_zero_ratio'] * 100:.2f}%")

        # 3. Direct FasterWhisperProvider call
        direct_provider = FasterWhisperProvider()
        direct_res = direct_provider.transcribe(raw_bytes, metadata)
        print(f"\n3. Direct FasterWhisperProvider Transcription:")
        print(f"   - Model: {direct_res.model_used}")
        print(f"   - Transcript: \"{direct_res.text}\"")
        print(f"   - Language: {direct_res.language} (Confidence: {direct_res.confidence:.2f})")
        print(f"   - Inference Time: {direct_res.duration_seconds:.2f}s")
        print(f"   - Quality Gate (is_valid_transcript): {is_valid_transcript(direct_res.text)}")

        # 4. Full Autopilot Orchestrator call (process_voice_input)
        orchestrator_analysis = default_voice_orchestrator.process_voice_input(
            audio_bytes=raw_bytes,
            filename=file_path,
            session_id=f"auto_voice_{int(time.time())}",
        )
        print(f"\n4. Full Autopilot Orchestrator (process_voice_input):")
        print(f"   - Analysis Status: {orchestrator_analysis.status.value}")
        print(f"   - Transcript Text: \"{orchestrator_analysis.transcript.text}\"")
        print(f"   - Sanitized Text: \"{orchestrator_analysis.transcript.sanitized_text}\"")
        print(f"   - Inferred Domain: {orchestrator_analysis.hints[0].category if orchestrator_analysis.hints else 'None'}")
        print(f"   - Candidate Tools: {orchestrator_analysis.hints[0].candidate_tools if orchestrator_analysis.hints else []}")
        print(f"   - Analysis Duration: {orchestrator_analysis.analysis_duration_ms} ms")

        # 5. Parity Comparison
        direct_match = (direct_res.text.strip().lower() == expected_text.strip().lower())
        orch_match = (orchestrator_analysis.transcript.text.strip().lower() == expected_text.strip().lower())
        status_ok = (orchestrator_analysis.status == VoiceStatus.COMPLETED)

        print(f"\n5. End-to-End Parity Evaluation:")
        print(f"   - Direct Provider Matches Expected: {direct_match}")
        print(f"   - Orchestrator Matches Expected:    {orch_match}")
        print(f"   - Orchestrator Status == COMPLETED: {status_ok}")
        print(f"   - Autopilot UI Branch: {'SUCCESS (What I heard card)' if (status_ok and is_valid_transcript(orchestrator_analysis.transcript.sanitized_text)) else 'FAILURE (Speech Not Understood)'}")

if __name__ == "__main__":
    audit_autopilot_voice_path()
