import io
import os
import sys
import time
import psutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from database.db import DatabaseManager
from ai.ollama_client import ollama_client
from ai.screenshot_analyzer import default_screenshot_analyzer
from ai.voice_transcriber import default_voice_transcriber
from modes.autopilot import default_autopilot_engine
from PIL import Image

print("=== WINFIX AI PERFORMANCE & RESOURCE BENCHMARK ===")
process = psutil.Process(os.getpid())
initial_ram_mb = process.memory_info().rss / (1024 * 1024)
cpu_start = process.cpu_percent(interval=0.1)

# 1. SQLite Query Latency
mgr = DatabaseManager(config.config.database_path)
times = []
for _ in range(50):
    t0 = time.perf_counter()
    with mgr.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, mode, status FROM sessions ORDER BY created_at DESC LIMIT 5;")
        _ = cur.fetchall()
    times.append(time.perf_counter() - t0)
avg_db_ms = (sum(times) / len(times)) * 1000
print(f"1. SQLite Query Latency (avg over 50 runs): {avg_db_ms:.3f} ms")

# 2. Autopilot Planning Latency
t0 = time.perf_counter()
plan = default_autopilot_engine.plan("My computer is running out of disk space on drive C")
autopilot_plan_ms = (time.perf_counter() - t0) * 1000
print(f"2. Autopilot Planning Latency: {autopilot_plan_ms:.2f} ms (steps: {len(plan.steps)})")

# 3. Voice Transcription Latency
test_wav = ROOT_DIR / "test_adapter.wav"
if test_wav.exists():
    with open(test_wav, "rb") as f:
        audio_bytes = f.read()
    t0 = time.perf_counter()
    transcript = default_voice_transcriber.transcribe_audio(audio_bytes, source_type="file")
    voice_latency_ms = (time.perf_counter() - t0) * 1000
    print(f"3. Voice Transcription Latency: {voice_latency_ms:.2f} ms ('{transcript.text}')")
else:
    print("3. Voice Transcription Latency: N/A (test_adapter.wav missing)")

# 4. Screenshot Vision Analysis Latency
img = Image.new("RGB", (400, 300), color=(30, 30, 30))
buf = io.BytesIO()
img.save(buf, format="PNG")
img_bytes = buf.getvalue()
t0 = time.perf_counter()
analysis = default_screenshot_analyzer.analyze_screenshot(img_bytes, filename="benchmark.png", user_question="test")
vision_latency_ms = (time.perf_counter() - t0) * 1000
print(f"4. Screenshot Analysis Latency: {vision_latency_ms:.2f} ms (status: {analysis.status})")

# 5. Local Ollama Text Response Latency
t0 = time.perf_counter()
ai_resp = ollama_client.generate(prompt="Status check", timeout=30)
text_latency_ms = (time.perf_counter() - t0) * 1000
print(f"5. Text AI Model (gemma4:12b) Latency: {text_latency_ms:.2f} ms (success: {ai_resp.get('success')})")

# 6. Resource Consumption
final_ram_mb = process.memory_info().rss / (1024 * 1024)
system_mem = psutil.virtual_memory()
cpu_end = process.cpu_percent(interval=0.2)

print("\n--- RESOURCE CONSUMPTION ---")
print(f"Python Process RAM: Initial={initial_ram_mb:.1f} MB, Final={final_ram_mb:.1f} MB (Delta: +{final_ram_mb-initial_ram_mb:.1f} MB)")
print(f"Host System RAM   : Total={system_mem.total/(1024**3):.2f} GB, Available={system_mem.available/(1024**3):.2f} GB, Used={system_mem.percent}%")
print(f"Process CPU Usage : {cpu_end:.1f}%")

