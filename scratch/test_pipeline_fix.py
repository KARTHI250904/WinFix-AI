import sys
import os

sys.path.insert(0, os.getcwd())
import numpy as np
from faster_whisper import WhisperModel
from ai.voice_transcriber import decode_audio_to_numpy, normalize_transcript_text

audio_path = r'C:\Users\karth\.gemini\antigravity\brain\c239b0a1-f291-4427-9137-fe6e0b806b6c\.user_uploaded\uploaded_media_1793264545231.wav'
with open(audio_path, 'rb') as f:
    audio_bytes = f.read()

arr, metrics = decode_audio_to_numpy(audio_bytes)

# Keep raw audio without scaling down
model = WhisperModel('base.en', device='cpu', compute_type='int8', local_files_only=True)

segs, info = model.transcribe(
    arr,
    beam_size=5,
    language='en',
    temperature=0.0,
    initial_prompt=None,
    condition_on_previous_text=False,
    vad_filter=False,
)

raw = ' '.join(s.text.strip() for s in segs)
print("Raw Whisper output on user audio:", repr(raw))

# Test proposed normalization
import re
t = raw
tech_replacements = {
    r"\b(?:your purpose|the purpose|you\'?re purpose)\s+(?:is\s+)?(?:broken|not working)\b": "Bluetooth is not working",
    r"\b(?:your purpose|the purpose|you\'?re purpose)\b": "Bluetooth",
    r"\bblue\s+tooth\b": "Bluetooth",
    r"\b(?:well-?serve|well-?served|will outserve|will now serve|wauserv|wau serv)(?:\s+service)?\b": "wuauserv service",
    r"\bwi-?fi\b": "Wi-Fi",
    r"\bbluetooth\b": "Bluetooth",
}
for p, c in tech_replacements.items():
    t = re.sub(p, c, t, flags=re.IGNORECASE)

print("Normalized output:", repr(t))

from agent.voice_diagnostics import default_voice_orchestrator
from agent.intent_classifier import default_intent_classifier

intent = default_intent_classifier.classify_intent(t)
print("Intent:", intent)
hints = default_voice_orchestrator.mapper.map_transcript_to_hints(t)
print("Hints:", [h.category for h in hints])
print("Tools:", [h.candidate_tools for h in hints])
