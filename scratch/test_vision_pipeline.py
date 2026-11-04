import io
import base64
import json
from PIL import Image, ImageDraw
from ai.ollama_client import ollama_client

img = Image.new('RGB', (500, 300), color=(240, 240, 240))
d = ImageDraw.Draw(img)
d.text((30, 30), 'Windows Update', fill=(0, 0, 0))
d.text((30, 70), 'There were some problems installing updates.', fill=(50, 50, 50))
d.text((30, 110), 'Error 0x80070422', fill=(200, 0, 0))
buf = io.BytesIO()
img.save(buf, format='PNG')
b64 = base64.b64encode(buf.getvalue()).decode()

print("Step 1: Running Moondream...")
v_resp = ollama_client.generate(
    prompt="Describe this Windows screenshot in detail. Read and transcribe all visible text, window titles, error dialogs, error messages, and error codes.",
    images=[b64],
    model="moondream",
    format=None,
    timeout=30
)
vision_text = v_resp.get("response", "").strip()
print("Vision text:", vision_text)

print("\nStep 2: Structuring with Gemma4:12b / Synthesis...")
s_prompt = f"""You are WinFix AI. Convert this visual description of a Windows screenshot into the required JSON schema.

Visual Description:
{vision_text}

JSON Schema:
{{
  "visible_facts_summary": "Concise summary of what is visually present in the image",
  "observations": [
    {{"category": "ERROR_MESSAGE", "text": "Exact text or symptom", "confidence": 0.95, "location": "screen"}}
  ],
  "detected_error_codes": ["0x80070422"],
  "detected_event_ids": [],
  "detected_applications": ["Windows Update"],
  "possible_interpretations": ["Windows Update service is not running or failed to connect."],
  "uncertainties": ["Screenshot only shows past UI state; cannot verify active background services without diagnostics."],
  "suggested_diagnostic_areas": ["windows_update"],
  "recommended_next_step": "Run read-only Windows Update health diagnostics to inspect the active service state."
}}
"""

g_resp = ollama_client.generate(
    prompt=s_prompt,
    model="gemma4:12b",
    format="json",
    timeout=20
)
print("Structured Output:", g_resp.get("response"))
