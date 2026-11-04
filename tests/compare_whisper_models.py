"""Controlled accuracy and performance benchmark between local faster-whisper models."""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faster_whisper import WhisperModel
from ai.voice_transcriber import decode_audio_to_numpy

TEST_FILES = [
    ("2026-10-02T15-38_audio.wav", "My Wi-Fi keeps disconnecting every few minutes."),
    ("test_perf_audio.wav", "My computer is very slow and the CPU usage is very high."),
    ("test_storage_audio.wav", "My C drive is almost full."),
]

PROMPT = "Windows technical troubleshooting: Wi-Fi network, Internet connection, CPU memory performance, C drive storage, Windows Update, error codes."

MODELS = ["tiny.en", "base.en"]

def run_comparison():
    print("=" * 70)
    print("FASTER-WHISPER LOCAL ACCURACY & BENCHMARK COMPARISON")
    print("=" * 70)

    for model_id in MODELS:
        print(f"\nEvaluating Model: {model_id}")
        t_load = time.time()
        try:
            model = WhisperModel(model_id, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            model = WhisperModel(model_id, device="cpu", compute_type="int8")
        load_time = time.time() - t_load
        print(f"Model Load Time: {load_time:.2f}s | Device: CPU | Compute: int8")
        print("-" * 70)

        for wav_path, expected in TEST_FILES:
            if not os.path.exists(wav_path):
                print(f"File {wav_path} not found.")
                continue

            raw_bytes = open(wav_path, "rb").read()
            arr, metrics = decode_audio_to_numpy(raw_bytes, target_sr=16000)

            t0 = time.time()
            segments_gen, info = model.transcribe(
                arr,
                beam_size=5,
                language="en",
                initial_prompt=PROMPT,
                vad_filter=False,
            )
            segments = list(segments_gen)
            infer_time = time.time() - t0

            transcript = " ".join(s.text.strip() for s in segments).strip()
            avg_lp = float(np.mean([s.avg_logprob for s in segments])) if segments else 0.0
            no_speech = float(np.mean([s.no_speech_prob for s in segments])) if segments else 0.0

            match = (transcript.lower().replace(".", "").replace("-", "") == 
                     expected.lower().replace(".", "").replace("-", ""))

            print(f"  Input: {wav_path} ({metrics['duration']:.2f}s audio)")
            print(f"  Expected: \"{expected}\"")
            print(f"  Actual:   \"{transcript}\"")
            print(f"  Inference Time: {infer_time:.2f}s | Avg LogProb: {avg_lp:.3f} | NoSpeechProb: {no_speech:.3f}")
            print(f"  Match: {'PASS (100% accurate)' if match else 'FAIL'}")
            print()

if __name__ == "__main__":
    run_comparison()
