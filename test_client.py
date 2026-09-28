"""Call the RunPod Serverless TTS endpoint and save the result as a WAV file.

Works on any computer (including the Intel Mac) - it only needs `pip install requests`.

    export RUNPOD_API_KEY="rpa_..."
    export RUNPOD_ENDPOINT_ID="abc123xyz"
    python test_client.py "আসসালামু আলাইকুম! আমি আপনাকে কীভাবে সাহায্য করতে পারি?" Charon out.wav
"""
import base64
import os
import sys
import time

import requests

API_KEY = os.environ["RUNPOD_API_KEY"]
ENDPOINT_ID = os.environ["RUNPOD_ENDPOINT_ID"]
BASE_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def tts(text, voice="Charon", out_path="out.wav", **options):
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/runsync", headers=HEADERS, timeout=300,
                      json={"input": {"text": text, "voice": voice, **options}})
    r.raise_for_status()
    job = r.json()
    # /runsync returns early with IN_QUEUE / IN_PROGRESS if the job takes long (e.g. a cold start) - poll until done
    while job.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
        time.sleep(2)
        job = requests.get(f"{BASE_URL}/status/{job['id']}", headers=HEADERS, timeout=30).json()
    if job.get("status") != "COMPLETED":
        raise RuntimeError(f"job failed: {job}")
    out = job["output"]
    if "error" in out:
        raise RuntimeError(out["error"])
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(out["audio_base64"]))
    print(f"saved {out_path}: {out['duration_sec']}s of audio, generated in {out['generation_sec']}s "
          f"(round trip {time.time() - t0:.1f}s)")
    return out_path


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "আসসালামু আলাইকুম! আমি আপনাকে কীভাবে সাহায্য করতে পারি?"
    voice = sys.argv[2] if len(sys.argv) > 2 else "Charon"
    out_path = sys.argv[3] if len(sys.argv) > 3 else "out.wav"
    tts(text, voice, out_path)
