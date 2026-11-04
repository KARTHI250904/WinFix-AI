import glob
import sys
import os

sys.path.insert(0, os.getcwd())
from faster_whisper import WhisperModel
from ai.voice_transcriber import decode_audio_to_numpy, normalize_transcript_text

model = WhisperModel('base.en', device='cpu', compute_type='int8', local_files_only=True)

all_files = sorted(glob.glob('scratch/audio_corpus/*.wav'))
print(f"Testing {len(all_files)} audio files with initial_prompt=None...")

for f in all_files:
    with open(f, 'rb') as fp:
        b = fp.read()
    arr, _ = decode_audio_to_numpy(b)
    segs, _ = model.transcribe(arr, initial_prompt=None, beam_size=5, language='en')
    raw = ' '.join(s.text.strip() for s in segs)
    norm = normalize_transcript_text(raw)
    print(f"{os.path.basename(f)}: \"{norm}\"")
