import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from ai.voice_transcriber import default_voice_transcriber, decode_audio_to_numpy
from agent.voice_diagnostics import default_voice_orchestrator
from agent.intent_classifier import default_intent_classifier

files = ['2026-10-02T15-38_audio.wav', 'test_adapter.wav', 'test_perf_audio.wav', 'test_storage_audio.wav']

for f in files:
    if not os.path.exists(f):
        print(f"File {f} not found")
        continue
    with open(f, 'rb') as fp:
        raw_bytes = fp.read()
    arr, metrics = decode_audio_to_numpy(raw_bytes)
    t0 = time.time()
    transcript = default_voice_transcriber.transcribe_audio(raw_bytes, source_type='file')
    t_proc = time.time() - t0
    intent = default_intent_classifier.classify_intent(transcript.sanitized_text)
    analysis = default_voice_orchestrator.process_voice_input(raw_bytes, filename=f)
    print("=" * 60)
    print(f"File: {f} ({len(raw_bytes)} bytes)")
    print(f"Decoded metrics: {metrics}")
    print(f"Audio duration: {transcript.duration_seconds}s")
    print(f"Transcription processing time: {transcript.processing_time_ms}ms (wall: {t_proc*1000:.1f}ms)")
    print(f"Model used: {transcript.model_used}")
    print(f"Transcript: \"{transcript.sanitized_text}\"")
    print(f"Confidence: {transcript.confidence}, Quality: {transcript.quality_status}")
    print(f"Classified Intent: {intent}")
    print(f"Inferred Domain: {[h.category for h in analysis.hints]}")
    print(f"Candidate Tools: {[h.candidate_tools for h in analysis.hints]}")
