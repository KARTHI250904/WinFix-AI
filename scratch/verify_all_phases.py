import os
import sys
import time
import json
import subprocess
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai.voice_transcriber import (
    FasterWhisperProvider,
    VoiceTranscriber,
    decode_audio_to_numpy,
    default_voice_transcriber,
    is_valid_transcript,
    normalize_transcript_text,
)
from agent.voice_diagnostics import (
    VoiceDiagnosticMapper,
    VoiceDiagnosticOrchestrator,
    default_voice_orchestrator,
)
from agent.intent_classifier import UserIntent, default_intent_classifier
from agent.tool_registry import default_tool_registry
from modes.personal_tutor import default_personal_tutor
from modes.autopilot import default_autopilot_engine
from input.voice_models import VoiceStatus, VoiceAnalysis

def levenshtein_distance(ref_tokens, hyp_tokens):
    d = np.zeros((len(ref_tokens) + 1, len(hyp_tokens) + 1), dtype=int)
    for i in range(len(ref_tokens) + 1):
        d[i, 0] = i
    for j in range(len(hyp_tokens) + 1):
        d[0, j] = j
    for i in range(1, len(ref_tokens) + 1):
        for j in range(1, len(hyp_tokens) + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                d[i, j] = d[i - 1, j - 1]
            else:
                d[i, j] = 1 + min(d[i - 1, j], d[i, j - 1], d[i - 1, j - 1])
    return d[len(ref_tokens), len(hyp_tokens)]

def compute_wer(ref: str, hyp: str) -> float:
    r_words = [w.strip(".,!?:;\"'()[]").lower() for w in ref.split() if w.strip(".,!?:;\"'()[]")]
    h_words = [w.strip(".,!?:;\"'()[]").lower() for w in hyp.split() if w.strip(".,!?:;\"'()[]")]
    if not r_words:
        return 0.0 if not h_words else 1.0
    dist = levenshtein_distance(r_words, h_words)
    return dist / len(r_words)

def compute_cer(ref: str, hyp: str) -> float:
    r_chars = list(ref.lower().strip())
    h_chars = list(hyp.lower().strip())
    if not r_chars:
        return 0.0 if not h_chars else 1.0
    dist = levenshtein_distance(r_chars, h_chars)
    return dist / len(r_chars)

# Synthesize audio file helper using SAPI
def synthesize_audio(text: str, filename: str) -> str:
    path = os.path.abspath(filename)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    clean_text = text.replace('"', '`"')
    ps_cmd = f"""
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.SetOutputToWaveFile('{path}')
$speak.Speak('{clean_text}')
$speak.Dispose()
"""
    ps_file = os.path.join(os.path.dirname(path), f"_synth_{os.path.basename(filename)}.ps1")
    with open(ps_file, "w", encoding="utf-8") as f:
        f.write(ps_cmd)
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_file], capture_output=True, check=True)
    if os.path.exists(ps_file):
        os.remove(ps_file)
    return path

print("================================================================================")
print("WINFIX AI — VOICE INTELLIGENCE & SPEECH RECOGNITION EXTENSIVE AUDIT")
print("================================================================================")

# 1. BASELINE SENTENCES (PHASE 4)
baseline_sentences = [
    ("My Wi-Fi keeps disconnecting every few minutes.", "NETWORK", UserIntent.DIAGNOSE),
    ("Why is my CPU running at 100 percent in Task Manager?", "PERFORMANCE", UserIntent.DIAGNOSE),
    ("My C drive is almost full and I need to free up disk space.", "STORAGE", UserIntent.DIAGNOSE),
    ("Bluetooth is not detecting my wireless headphones.", "BLUETOOTH", UserIntent.DIAGNOSE),
    ("Windows Update failed to install with error code 0x80070422.", "WINDOWS_UPDATE", UserIntent.DIAGNOSE),
    ("Google Chrome crashed and is not opening anymore.", "APPLICATION_CRASH", UserIntent.DIAGNOSE),
    ("The wuauserv service is stopped and will not start.", "WINDOWS_UPDATE", UserIntent.DIAGNOSE),
    ("How do I view my previous Windows Update failures?", "WINDOWS_UPDATE", UserIntent.VIEW_HISTORY),
    ("My Wi-Fi is connected but says no internet access.", "NETWORK", UserIntent.DIAGNOSE),
    ("Can you check if Windows Defender real-time protection is turned on?", "DEFENDER", UserIntent.CHECK_STATUS),
]

# 2. UNSEEN SENTENCES (PHASE 5)
unseen_sentences = [
    ("My printer is showing as offline and printing nothing.", "GENERAL", UserIntent.DIAGNOSE),
    ("The laptop fans are loud and Windows is freezing up.", "PERFORMANCE", UserIntent.DIAGNOSE),
    ("I have a yellow exclamation mark on my graphics driver.", "GENERAL", UserIntent.DIAGNOSE),
    ("Need to clean up temp files because C drive has zero space.", "STORAGE", UserIntent.REPAIR),
    ("DNS server is not responding when browsing websites.", "NETWORK", UserIntent.DIAGNOSE),
    ("Audio service is not running and there is a red cross on volume.", "SERVICE", UserIntent.DIAGNOSE),
    ("Blue screen of death occurred with system thread exception not handled.", "APPLICATION_CRASH", UserIntent.DIAGNOSE),
    ("How can I see what is taking up my RAM memory?", "PERFORMANCE", UserIntent.CHECK_STATUS),
    ("Disable Bluetooth and turn on airplane mode.", "BLUETOOTH", UserIntent.CONFIGURE),
    ("Restart wuauserv service to fix failed updates.", "WINDOWS_UPDATE", UserIntent.REPAIR),
]

os.makedirs("scratch/audio_corpus", exist_ok=True)

results_baseline = []
results_unseen = []

print("\n--- PHASE 4: 10 BASELINE SENTENCES BENCHMARK ---")
for idx, (target_text, expected_domain, expected_intent) in enumerate(baseline_sentences, 1):
    audio_path = f"scratch/audio_corpus/baseline_{idx:02d}.wav"
    synthesize_audio(target_text, audio_path)
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    
    t0 = time.time()
    transcript = default_voice_transcriber.transcribe_audio(audio_bytes, source_type="microphone")
    proc_time_ms = transcript.processing_time_ms
    rec_text = transcript.sanitized_text
    
    wer = compute_wer(target_text, rec_text)
    cer = compute_cer(target_text, rec_text)
    
    inferred_intent = default_intent_classifier.classify_intent(rec_text)
    analysis = default_voice_orchestrator.process_voice_input(audio_bytes, filename=f"baseline_{idx:02d}.wav")
    detected_domains = [h.category for h in analysis.hints]
    domain_match = (expected_domain in detected_domains) or (expected_domain == "WINDOWS_UPDATE" and "SERVICE" in detected_domains) or (expected_domain == "GENERAL" and "GENERAL" in detected_domains)
    intent_match = (inferred_intent == expected_intent)

    res_item = {
        "id": f"B{idx:02d}",
        "target": target_text,
        "recognized": rec_text,
        "wer": wer,
        "cer": cer,
        "audio_dur_s": transcript.duration_seconds,
        "proc_time_ms": proc_time_ms,
        "expected_domain": expected_domain,
        "detected_domains": detected_domains,
        "domain_match": domain_match,
        "expected_intent": expected_intent.value,
        "detected_intent": inferred_intent.value,
        "intent_match": intent_match,
        "confidence": transcript.confidence,
    }
    results_baseline.append(res_item)
    print(f"[{res_item['id']}] Target: \"{target_text}\"")
    print(f"      Heard:  \"{rec_text}\"")
    print(f"      WER: {wer:.2%} | CER: {cer:.2%} | Dur: {transcript.duration_seconds}s | Proc: {proc_time_ms}ms")
    print(f"      Domain: {detected_domains} (Expected: {expected_domain} -> {'PASS' if domain_match else 'FAIL'})")
    print(f"      Intent: {inferred_intent.value} (Expected: {expected_intent.value} -> {'PASS' if intent_match else 'FAIL'})")

print("\n--- PHASE 5: 10 UNSEEN SENTENCES BENCHMARK ---")
for idx, (target_text, expected_domain, expected_intent) in enumerate(unseen_sentences, 1):
    audio_path = f"scratch/audio_corpus/unseen_{idx:02d}.wav"
    synthesize_audio(target_text, audio_path)
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    
    t0 = time.time()
    transcript = default_voice_transcriber.transcribe_audio(audio_bytes, source_type="microphone")
    proc_time_ms = transcript.processing_time_ms
    rec_text = transcript.sanitized_text
    
    wer = compute_wer(target_text, rec_text)
    cer = compute_cer(target_text, rec_text)
    
    inferred_intent = default_intent_classifier.classify_intent(rec_text)
    analysis = default_voice_orchestrator.process_voice_input(audio_bytes, filename=f"unseen_{idx:02d}.wav")
    detected_domains = [h.category for h in analysis.hints]
    domain_match = (expected_domain in detected_domains) or (expected_domain == "SERVICE" and ("WINDOWS_UPDATE" in detected_domains or "SERVICE" in detected_domains)) or (expected_domain == "GENERAL" and "GENERAL" in detected_domains)
    intent_match = (inferred_intent == expected_intent)

    res_item = {
        "id": f"U{idx:02d}",
        "target": target_text,
        "recognized": rec_text,
        "wer": wer,
        "cer": cer,
        "audio_dur_s": transcript.duration_seconds,
        "proc_time_ms": proc_time_ms,
        "expected_domain": expected_domain,
        "detected_domains": detected_domains,
        "domain_match": domain_match,
        "expected_intent": expected_intent.value,
        "detected_intent": inferred_intent.value,
        "intent_match": intent_match,
        "confidence": transcript.confidence,
    }
    results_unseen.append(res_item)
    print(f"[{res_item['id']}] Target: \"{target_text}\"")
    print(f"      Heard:  \"{rec_text}\"")
    print(f"      WER: {wer:.2%} | CER: {cer:.2%} | Dur: {transcript.duration_seconds}s | Proc: {proc_time_ms}ms")
    print(f"      Domain: {detected_domains} (Expected: {expected_domain} -> {'PASS' if domain_match else 'FAIL'})")
    print(f"      Intent: {inferred_intent.value} (Expected: {expected_intent.value} -> {'PASS' if intent_match else 'FAIL'})")

# Save summary metrics to json
with open("scratch/voice_benchmarks.json", "w", encoding="utf-8") as f:
    json.dump({"baseline": results_baseline, "unseen": results_unseen}, f, indent=2)

print("\n--- BENCHMARK COMPLETE. RESULTS SAVED TO scratch/voice_benchmarks.json ---")
