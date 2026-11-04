"""Cross-mode verification test for Personal Tutor, Autopilot, and Voice Diagnostics."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.voice_diagnostics import default_voice_orchestrator
from ai.voice_transcriber import is_valid_transcript, decode_audio_to_numpy
from input.voice_models import VoiceStatus

SCENARIOS = [
    ("Personal Tutor", "2026-10-02T15-38_audio.wav", "My Wi-Fi keeps disconnecting every few minutes.", "NETWORK"),
    ("Personal Tutor", "test_perf_audio.wav", "My computer is very slow and the CPU usage is very high.", "PERFORMANCE"),
    ("Voice Diagnostics", "test_storage_audio.wav", "My C drive is almost full.", "STORAGE"),
    ("Autopilot", "test_adapter.wav", "My adapter is not working properly, what can I do?", "NETWORK"),
]

def run_cross_mode_tests():
    print("=" * 80)
    print("WINFIX AI — CROSS-MODE VOICE INPUT VERIFICATION & ACCEPTANCE TEST")
    print("=" * 80)

    all_passed = True

    for mode_name, wav_file, expected_text, expected_domain in SCENARIOS:
        if not os.path.exists(wav_file):
            print(f"Skipping {wav_file} (not found)")
            continue

        raw_bytes = open(wav_file, "rb").read()
        audio_arr, metrics = decode_audio_to_numpy(raw_bytes, 16000)

        t0 = time.time()
        analysis = default_voice_orchestrator.process_voice_input(
            audio_bytes=raw_bytes,
            filename=wav_file,
            session_id=f"test_{mode_name.lower().replace(' ', '_')}_{int(time.time())}",
        )
        elapsed_ms = int((time.time() - t0) * 1000)

        transcript = analysis.transcript.sanitized_text
        status_ok = (analysis.status == VoiceStatus.COMPLETED)
        valid_trans = is_valid_transcript(transcript)
        domain = analysis.hints[0].category if analysis.hints else "UNKNOWN"
        domain_ok = (domain == expected_domain)
        text_match = (transcript.strip().lower().replace(".", "").replace("-", "") == 
                      expected_text.strip().lower().replace(".", "").replace("-", ""))

        print(f"\n[MODE: {mode_name}]")
        print(f"  • Input Audio: {wav_file} ({metrics['duration']:.2f}s, {metrics['sample_count']} samples, RMS={metrics['rms']:.4f})")
        print(f"  • Expected Text:   \"{expected_text}\"")
        print(f"  • Actual Text:     \"{transcript}\"")
        print(f"  • Expected Domain: {expected_domain}")
        print(f"  • Actual Domain:   {domain}")
        print(f"  • Status:          {analysis.status.value} | Valid Quality: {valid_trans}")
        print(f"  • Candidate Tools: {analysis.hints[0].candidate_tools if analysis.hints else []}")
        print(f"  • Execution Time:  {elapsed_ms} ms")

        passed = status_ok and valid_trans and domain_ok and text_match
        print(f"  • Verification:    {'PASS (REAL_PASS)' if passed else 'FAIL'}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 80)
    print(f"FINAL CROSS-MODE RESULT: {'ALL PASS' if all_passed else 'SOME FAILED'}")
    print("=" * 80)
    return all_passed

if __name__ == "__main__":
    success = run_cross_mode_tests()
    sys.exit(0 if success else 1)
