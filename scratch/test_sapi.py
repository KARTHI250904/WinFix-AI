import os
import subprocess
import sys

ps_script = """
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.SetOutputToWaveFile("$pwd/scratch/test_tts.wav")
$speak.Speak("Testing Windows speech synthesis for voice verification.")
$speak.Dispose()
"""

with open("scratch/gen.ps1", "w", encoding="utf-8") as f:
    f.write(ps_script)

res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "scratch/gen.ps1"], capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
print("File exists:", os.path.exists("scratch/test_tts.wav"))
if os.path.exists("scratch/test_tts.wav"):
    print("File size:", os.path.getsize("scratch/test_tts.wav"))
