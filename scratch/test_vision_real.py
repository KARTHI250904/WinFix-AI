import io
import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

print("=== REAL OFFLINE SCREENSHOT PIPELINE AUDIT ===")

# 1. Create a synthetic realistic Windows 11 Quick Settings screenshot
img = Image.new("RGB", (600, 400), color=(32, 32, 32))
draw = ImageDraw.Draw(img)

# Draw Quick Settings panel tiles
# Tile 1: Wi-Fi Connected (Blue active tile)
draw.rectangle([40, 40, 260, 120], fill=(0, 103, 192), outline=(100, 100, 100))
draw.text((60, 60), "Wi-Fi", fill=(255, 255, 255))
draw.text((60, 85), "Connected to Home_5G", fill=(220, 220, 220))

# Tile 2: Airplane Mode (Grey inactive tile)
draw.rectangle([300, 40, 520, 120], fill=(45, 45, 45), outline=(70, 70, 70))
draw.text((320, 60), "Airplane mode", fill=(255, 255, 255))
draw.text((320, 85), "Off", fill=(180, 180, 180))

# Tile 3: Night Light (Grey inactive tile)
draw.rectangle([40, 150, 260, 230], fill=(45, 45, 45), outline=(70, 70, 70))
draw.text((60, 170), "Night light", fill=(255, 255, 255))
draw.text((60, 195), "Off", fill=(180, 180, 180))

# Tile 4: Battery Saver (Grey inactive tile)
draw.rectangle([300, 150, 520, 230], fill=(45, 45, 45), outline=(70, 70, 70))
draw.text((320, 170), "Energy saver", fill=(255, 255, 255))
draw.text((320, 195), "Off", fill=(180, 180, 180))

# Notice: Bluetooth tile is MISSING!

buf = io.BytesIO()
img.save(buf, format="PNG")
img_bytes = buf.getvalue()
test_img_path = ROOT_DIR / "scratch" / "test_quick_settings_no_bluetooth.png"
with open(test_img_path, "wb") as f:
    f.write(img_bytes)

print(f"Created test screenshot: {test_img_path} ({len(img_bytes)} bytes)")

# 2. Run real vision analysis through default_screenshot_analyzer
from ai.screenshot_analyzer import default_screenshot_analyzer

t0 = time.time()
print("Executing real Moondream vision inference via local Ollama...")
analysis = default_screenshot_analyzer.analyze_screenshot(
    image_bytes=img_bytes,
    filename="test_quick_settings_no_bluetooth.png",
    user_question="Bluetooth icon is missing from quick settings",
    session_id="test_vision_sess",
)
duration = time.time() - t0
print(f"Vision analysis completed in {duration:.2f}s")
print(f"Status: {analysis.status}")
print(f"Model used: {analysis.model_used}")
print(f"Visible facts summary:\n{analysis.visible_facts_summary}")
print(f"Diagnostic hints: {[(h.tool_name, h.risk_level, h.purpose) for h in analysis.diagnostic_hints]}")
print(f"Observations: {analysis.evidence.observations}")
print(f"Raw text extracted: {analysis.evidence.raw_text_extracted}")
print(f"Detected error codes: {analysis.evidence.detected_error_codes}")
print(f"Privacy warnings: {analysis.privacy_warnings}")
print(f"Uncertainties: {analysis.uncertainties}")
print(f"Recommended next step: {analysis.recommended_next_step}")
