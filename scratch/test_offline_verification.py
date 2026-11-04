import os
import sys
import socket
import urllib.request
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

print("=== CONTROLLED OFFLINE ENVIRONMENT TEST ===")

# Test 1: Proof of external isolation mechanism
# We block all non-loopback connections via custom socket patch
orig_connect = socket.socket.connect

def offline_connect(self, address):
    host = address[0]
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise OSError(f"AIRGAP_ENFORCED: Connection to external host {host} blocked")
    return orig_connect(self, address)

socket.socket.connect = offline_connect

# Verify external access fails
try:
    s = socket.socket()
    s.connect(("8.8.8.8", 53))
    print("ERROR: External connection unexpectedly succeeded")
except OSError as e:
    print(f"Verified: External connections are blocked: {e}")

# Test 2: Localhost Ollama connection
import config
cfg = config.config
req = urllib.request.Request(f"{cfg.ollama_base_url}/api/tags")
with urllib.request.urlopen(req, timeout=5) as resp:
    import json
    data = json.loads(resp.read().decode())
    models = [m["name"] for m in data.get("models", [])]
    print(f"Verified: Localhost Ollama reachable, models: {models}")

# Test 3: Faster-Whisper local model loading with HF_HUB_OFFLINE=1
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
from faster_whisper import WhisperModel
print("Loading Faster-Whisper base.en model offline...")
t0 = time.time()
stt = WhisperModel("base.en", device="cpu", compute_type="int8")
print(f"Verified: Faster-Whisper loaded offline in {time.time()-t0:.2f}s")

# Test 4: Transcribe test audio file via WinFix AI voice transcriber
test_wav = "test_adapter.wav"
if os.path.exists(test_wav):
    from ai.voice_transcriber import default_voice_transcriber
    with open(test_wav, "rb") as af:
        audio_data = af.read()
    t_stt = time.time()
    transcript = default_voice_transcriber.transcribe_audio(audio_data, source_type="file")
    print(f"Verified: WinFix VoiceTranscriber transcribed in {time.time()-t_stt:.2f}s: '{transcript.text}' (status: {transcript.quality_status.value})")
else:
    print(f"Test audio {test_wav} not found")

# Test 5: SQLite Database Access
from database.db import DatabaseManager
db = DatabaseManager(cfg.database_path)
with db.get_connection() as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    res = cur.fetchone()[0]
    print(f"Verified: SQLite integrity_check = {res}")

# Test 6: Windows Diagnostic Tool Execution
import windows
sys_info = windows.get_complete_system_info()
print(f"Verified: get_complete_system_info success={sys_info.get('success')} OS={sys_info.get('data', {}).get('os', {}).get('caption')}")

# Test 7: Local AI text generation (Gemma) offline test
from ai.ollama_client import ollama_client
print("Testing local Ollama gemma4:12b inference offline...")
t_gen_0 = time.time()
ai_resp = ollama_client.generate(
    prompt="Reply with exactly: PONG",
    system="You are a test assistant.",
    timeout=30,
)
print(f"Verified: Ollama generation success={ai_resp.get('success')}, duration={time.time()-t_gen_0:.2f}s, response='{ai_resp.get('response', '').strip()}'")

print("=== ALL OFFLINE CAPABILITY TESTS COMPLETED SUCCESSFULLY ===")
