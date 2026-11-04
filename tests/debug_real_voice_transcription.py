"""Developer diagnostic tool for real voice transcription.

Inspects audio samples, PCM decoding via PyAV, FasterWhisper model state,
VAD behavior, segment generation, and final transcript assembly.
"""

import argparse
import io
import os
import sys
import time
from typing import Optional

import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.voice_transcriber import FasterWhisperProvider, decode_audio_to_numpy, VoiceMetadata
from input.voice_models import VoiceStatus


def analyze_and_transcribe_wav(file_path: str, model_size: str = "tiny.en", use_vad: bool = False):
    print("=" * 60)
    print("WINFIX AI — REAL VOICE TRANSCRIPTION DIAGNOSTICS")
    print("=" * 60)
    print(f"File Path: {file_path}")

    if not os.path.exists(file_path):
        print(f"ERROR: File '{file_path}' does not exist.")
        return False

    raw_bytes = open(file_path, "rb").read()
    file_size = len(raw_bytes)
    print(f"File Size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")

    # 1. Decode PCM audio using PyAV / native pipeline
    t_dec_start = time.time()
    audio_arr, metrics = decode_audio_to_numpy(raw_bytes, target_sr=16000)
    dec_duration = time.time() - t_dec_start

    print("\n--- 1. DECODED PCM PROPERTIES ---")
    print(f"Decoder: PyAV / wave fallback (resampled to 16,000 Hz)")
    print(f"Decode Duration: {dec_duration * 1000:.2f} ms")
    print(f"Sample Count: {metrics.get('sample_count', len(audio_arr)):,}")
    print(f"Duration (seconds): {metrics.get('duration', 0.0):.2f}s")
    print(f"NumPy dtype: {audio_arr.dtype}")
    print(f"NumPy shape: {audio_arr.shape}")
    print(f"Min Sample Amplitude: {float(np.min(audio_arr)) if audio_arr.size > 0 else 0.0:.4f}")
    print(f"Max Sample Amplitude: {metrics.get('max_abs', 0.0):.4f}")
    print(f"Mean Abs Amplitude: {float(np.mean(np.abs(audio_arr))) if audio_arr.size > 0 else 0.0:.4f}")
    print(f"RMS Power: {metrics.get('rms', 0.0):.4f}")
    print(f"Non-zero Sample Ratio: {metrics.get('non_zero_ratio', 0.0) * 100:.2f}%")

    if audio_arr.size == 0:
        print("ERROR: Decoded audio is empty!")
        return False

    if metrics.get("max_abs", 0.0) < 0.001:
        print("WARNING: Decoded audio is silent or near-zero!")

    # 2. Initialize WhisperModel
    print("\n--- 2. WHISPER MODEL INITIALIZATION ---")
    print(f"Requested Model Size: {model_size}")
    provider = FasterWhisperProvider(model_size=model_size)
    
    if not provider.is_available():
        print("ERROR: faster-whisper is not available in current environment.")
        return False

    t_mod_start = time.time()
    model = provider._get_model()
    mod_load_time = time.time() - t_mod_start
    print(f"Model Load Time: {mod_load_time:.2f}s")
    print(f"Device: cpu, Compute Type: int8")

    # 3. Transcribe audio with Whisper
    print("\n--- 3. WHISPER TRANSCRIPTION ---")
    print(f"VAD Filter: {'ENABLED' if use_vad else 'DISABLED'}")
    print(f"Beam Size: 5")

    t_tr_start = time.time()
    segments_gen, info = model.transcribe(
        audio_arr,
        beam_size=5,
        language=None,
        vad_filter=use_vad,
    )

    detected_lang = getattr(info, "language", "unknown")
    lang_prob = getattr(info, "language_probability", 0.0)
    print(f"Detected Language: {detected_lang} (probability: {lang_prob:.2f})")

    segments = list(segments_gen)
    tr_duration = time.time() - t_tr_start
    print(f"Transcription Duration: {tr_duration:.2f}s")
    print(f"Segment Count: {len(segments)}")

    print("\n--- 4. RETURNED SEGMENTS ---")
    segment_texts = []
    for idx, seg in enumerate(segments, 1):
        print(f"  [{idx}] [{seg.start:.2f}s -> {seg.end:.2f}s] avg_logprob={seg.avg_logprob:.3f} no_speech_prob={seg.no_speech_prob:.3f}: \"{seg.text.strip()}\"")
        clean_text = seg.text.strip()
        if clean_text:
            segment_texts.append(clean_text)

    final_transcript = " ".join(segment_texts).strip()
    print("\n--- 5. FINAL ASSEMBLED TRANSCRIPT ---")
    print(f"Transcript: \"{final_transcript}\"")
    print(f"Valid Transcript Quality Gate: {'PASS' if len(final_transcript) >= 2 else 'FAIL'}")

    print("=" * 60)
    return len(final_transcript) > 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WinFix AI Voice Transcription Debugger")
    parser.add_argument("wav_path", nargs="?", default="2026-10-02T15-38_audio.wav", help="Path to WAV file")
    parser.add_argument("--model", default="tiny.en", help="faster-whisper model size (e.g. tiny.en, base.en, small.en)")
    parser.add_argument("--vad", action="store_true", help="Enable VAD filter")
    args = parser.parse_args()

    success = analyze_and_transcribe_wav(args.wav_path, model_size=args.model, use_vad=args.vad)
    sys.exit(0 if success else 1)
