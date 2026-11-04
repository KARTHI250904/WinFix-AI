import sys
import os

sys.path.insert(0, os.path.abspath("."))

print("=== Python Environment ===")
print("sys.executable:", sys.executable)
print("sys.version:", sys.version)
print("Current Working Directory:", os.getcwd())

packages = ['faster_whisper', 'ctranslate2', 'av', 'streamlit', 'PIL', 'requests', 'yaml']
print("\n=== Package Inspections ===")
for pkg in packages:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, "__version__", "unknown")
        file_path = getattr(mod, "__file__", "unknown")
        print(f"[OK] {pkg}: v{ver} @ {file_path}")
    except Exception as ex:
        print(f"[FAIL] {pkg}: {type(ex).__name__} - {ex}")

print("\n=== FasterWhisper Model Check ===")
try:
    from faster_whisper import WhisperModel
    print("WhisperModel class imported successfully.")
    
    # Try initializing the model
    print("Testing WhisperModel('tiny.en', device='cpu', compute_type='int8')...")
    model = WhisperModel('tiny.en', device='cpu', compute_type='int8')
    print("[SUCCESS] WhisperModel initialized successfully:", model)
except Exception as ex:
    print(f"[FAILURE] WhisperModel initialization failed: {type(ex).__name__} - {ex}")
    import traceback
    traceback.print_exc()

print("\n=== WinFix Transcriber Check ===")
try:
    from ai.voice_transcriber import FasterWhisperProvider, VoiceTranscriber, default_voice_transcriber
    from agent.voice_diagnostics import default_voice_orchestrator
    
    provider = FasterWhisperProvider()
    print("FasterWhisperProvider.is_available():", provider.is_available())
    print("default_voice_transcriber.is_available():", default_voice_transcriber.is_available())
    print("default_voice_orchestrator.transcriber.is_available():", default_voice_orchestrator.transcriber.is_available())
except Exception as ex:
    print(f"[FAILURE] WinFix Transcriber check failed: {type(ex).__name__} - {ex}")
    import traceback
    traceback.print_exc()
