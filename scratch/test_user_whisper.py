import sys, os
sys.path.insert(0, os.getcwd())
from faster_whisper import WhisperModel
from ai.voice_transcriber import decode_audio_to_numpy

audio_path = r'C:\Users\karth\.gemini\antigravity\brain\c239b0a1-f291-4427-9137-fe6e0b806b6c\.user_uploaded\uploaded_media_1793264545231.wav'
with open(audio_path, 'rb') as f:
    audio_bytes = f.read()
arr, metrics = decode_audio_to_numpy(audio_bytes)

model = WhisperModel('base.en', device='cpu', compute_type='int8', local_files_only=True)

for cond in [True, False]:
    for temp in [0.0, 0.2]:
        for beam in [1, 5]:
            segs, info = model.transcribe(arr, condition_on_previous_text=cond, temperature=temp, beam_size=beam, language='en')
            res = " ".join(s.text.strip() for s in segs)
            print(f"cond={cond}, temp={temp}, beam={beam}: {repr(res)}")
