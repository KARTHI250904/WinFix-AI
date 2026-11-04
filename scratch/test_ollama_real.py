import sys
import time
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai.ollama_client import ollama_client
print("Testing Ollama with gemma4:12b (timeout=120s)...")
t0 = time.time()
res = ollama_client.generate(prompt="Say OK", timeout=120)
print(f"Done in {time.time()-t0:.2f}s: success={res.get('success')} response='{res.get('response', '').strip()}'")

