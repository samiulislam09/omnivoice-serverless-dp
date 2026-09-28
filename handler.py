"""RunPod Serverless worker: Bengali TTS with the fine-tuned OmniVoice model from Hugging Face.

Input  (job["input"]): {"text": "...", "voice": "Charon" | "Kore", "num_step": 32, "speed": 1.0, "language": "bn"}
Output:                {"audio_base64": "<WAV bytes, base64>", "format": "wav", "sample_rate": 24000, ...}
"""
import base64
import io
import os
import time
from pathlib import Path

# Keep Hugging Face downloads on the network volume when one is attached, so new workers don't re-download.
if Path("/runpod-volume").is_dir():
    os.environ.setdefault("HF_HOME", "/runpod-volume/hf_cache")

import runpod
import soundfile as sf
import torch
from huggingface_hub import hf_hub_download
from omnivoice import OmniVoice

HF_REPO_ID = os.environ.get("HF_REPO_ID", "sawon19/omnivoice-bengali")
HF_TOKEN = os.environ.get("HF_TOKEN") or None          # needed because the model repo is private
VOICES = [v.strip() for v in os.environ.get("VOICES", "Charon,Kore").split(",") if v.strip()]
MAX_CHARS = int(os.environ.get("MAX_CHARS", "2000"))
SAMPLE_RATE = 24000

# ---- cold start: runs once per worker, then every request reuses the loaded model ----
t0 = time.time()
MODEL = OmniVoice.from_pretrained(HF_REPO_ID, device_map="cuda:0", dtype=torch.float16, token=HF_TOKEN)
PROMPTS = {}
for voice in VOICES:
    ref_wav = hf_hub_download(HF_REPO_ID, f"reference_voices/{voice}.wav", token=HF_TOKEN)
    ref_txt = Path(hf_hub_download(HF_REPO_ID, f"reference_voices/{voice}.txt", token=HF_TOKEN))
    PROMPTS[voice] = MODEL.create_voice_clone_prompt(ref_audio=ref_wav, ref_text=ref_txt.read_text(encoding="utf-8").strip())
print(f"loaded {HF_REPO_ID} with voices {sorted(PROMPTS)} in {time.time() - t0:.1f}s", flush=True)


def handler(job):
    inp = job.get("input") or {}
    text = str(inp.get("text", "")).strip()
    voice = inp.get("voice", VOICES[0])
    if not text:
        return {"error": "input.text is required"}
    if len(text) > MAX_CHARS:
        return {"error": f"text is too long ({len(text)} > {MAX_CHARS} characters)"}
    if voice not in PROMPTS:
        return {"error": f"unknown voice {voice!r}; available: {sorted(PROMPTS)}"}

    kwargs = {}
    if "num_step" in inp:          # fewer steps = faster, e.g. 16 (default 32)
        kwargs["num_step"] = int(inp["num_step"])
    if "speed" in inp:             # e.g. 0.9 slower, 1.1 faster
        kwargs["speed"] = float(inp["speed"])

    t = time.time()
    audio = MODEL.generate(text=text, language=inp.get("language", "bn"),
                           voice_clone_prompt=PROMPTS[voice], **kwargs)[0]
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return {
        "audio_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "format": "wav",
        "sample_rate": SAMPLE_RATE,
        "duration_sec": round(len(audio) / SAMPLE_RATE, 2),
        "generation_sec": round(time.time() - t, 2),
        "voice": voice,
    }


runpod.serverless.start({"handler": handler})
