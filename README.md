# Run the Bengali OmniVoice model on RunPod Serverless

This guide deploys your fine-tuned model (`sawon19/omnivoice-bengali` on Hugging Face) as a **RunPod Serverless endpoint**. You send text and a voice name over HTTP, and you get a WAV file back. You pay only for the seconds a GPU is working. When there's no traffic it scales to zero and costs almost nothing.

```
your app / script ──HTTP──▶ RunPod Serverless endpoint ──▶ GPU worker (handler.py)
                                                              │ on cold start: downloads your model
                                                              ▼ from Hugging Face, keeps it in memory
                              ◀── {"audio_base64": "...WAV..."}
```

**Files in this folder**

| File | What it is |
|---|---|
| `handler.py` | The worker code. It loads the model once, then turns each request into a WAV |
| `requirements.txt` | Python packages: RunPod SDK, OmniVoice (the same pinned version you trained with), torch 2.8 |
| `Dockerfile` | Builds the worker image. RunPod builds it for you from GitHub, so you don't need Docker on your Mac |
| `test_client.py` | A small script that calls the endpoint and saves `out.wav`. It works on your Intel Mac |

> ⚠️ **Licence:** OmniVoice's base weights are **CC-BY-NC (non-commercial)**, and your fine-tune inherits that. Don't use this endpoint for a commercial product unless you have permission from the model's authors.

> RunPod's website changes from time to time. If a button or menu name below doesn't match exactly, look for the closest equivalent.

---

## Step 1: Things you need

1. **A RunPod account with credit** (Billing → add a few dollars).
2. **A RunPod API key:** RunPod → **Settings → API Keys → Create API Key**. Give it read/write access (or at least permission to call Serverless endpoints) and copy it. It starts with `rpa_`.
3. **A new Hugging Face token (Read access):** <https://huggingface.co/settings/tokens> → *Create new token* → type **Read**.
   *Revoke the old token that was pasted into the chat earlier.*
4. **A GitHub account.** RunPod builds the worker directly from a GitHub repo.

---

## Step 2: Put this folder on GitHub (private repo)

1. On GitHub, click **New repository**, name it e.g. `omnivoice-bengali-serverless`, choose **Private**, and create it without a README.
2. In Terminal on your Mac:
   ```bash
   cd /Volumes/work/dataset/runpod_serverless
   git init
   git add handler.py requirements.txt Dockerfile test_client.py README.md
   git commit -m "OmniVoice Bengali RunPod serverless worker"
   git branch -M main
   git remote add origin https://github.com/<your-github-username>/omnivoice-bengali-serverless.git
   git push -u origin main
   ```
   There are no secrets in these files. The Hugging Face token goes into RunPod in the next step, not into code.

---

## Step 3: Store the Hugging Face token as a RunPod secret

1. RunPod → **Secrets** (under *Settings* or the left menu) → **Create Secret**.
2. Name it `hf_token` and paste the **new Read token** as the value. Save.

You'll reference it later as `{{ RUNPOD_SECRET_hf_token }}`, so the token is never written anywhere in plain text.

---

## Step 4 (optional but recommended): Create a network volume for the model cache

Without a volume, every **new** worker downloads the model (~3 GB) from Hugging Face when it starts, which adds roughly 30–60 s to that first request. With a volume, the model is downloaded once and reused.

1. RunPod → **Storage → New Network Volume**.
2. Choose a data centre that has **16 GB / 24 GB GPUs** available. Size: **15 GB** is enough. Name: `omnivoice-cache`.
3. `handler.py` detects the volume automatically. It's mounted at `/runpod-volume` and the model is cached in `/runpod-volume/hf_cache`.

**Trade-off:** a volume locks the endpoint to that one data centre, which means fewer GPUs to choose from, so you may wait longer when GPUs are busy. If requests sit "in queue" for a long time, remove the volume.

---

## Step 5: Create the Serverless endpoint

1. RunPod → **Serverless → New Endpoint**.
2. Choose **GitHub Repo** as the source. Connect your GitHub account the first time, then pick `omnivoice-bengali-serverless`, branch `main`, and Dockerfile path `Dockerfile`.
3. Configure it:

| Setting | Value | Why |
|---|---|---|
| **GPU** | **16 GB** tier (e.g. RTX A4000 / 4000 Ada), with **24 GB** as a second choice | The 0.6B model needs only a few GB. Pick the cheapest tiers that have availability |
| **Active (min) workers** | **0** | Scale to zero, so you pay nothing when idle |
| **Max workers** | **1–3** | Upper limit on parallel requests and cost |
| **Idle timeout** | **60 s** or more | How long a worker stays warm after a request. Longer means fewer cold starts but more cost |
| **Execution timeout** | **300 s** | Covers a cold start plus long texts |
| **FlashBoot** | **On** | Much faster restarts of recently used workers |
| **Container disk** | **20 GB** | Room for the image and the model download |
| **Network volume** | `omnivoice-cache` (if you made one in step 4) | |
| **Environment variables** | see below | |

**Environment variables:**

| Key | Value |
|---|---|
| `HF_TOKEN` | `{{ RUNPOD_SECRET_hf_token }}` |
| `HF_REPO_ID` | `sawon19/omnivoice-bengali` |
| `VOICES` | `Charon,Kore` *(optional; this is the default)* |
| `MAX_CHARS` | `2000` *(optional; the longest text allowed per request)* |

4. Click **Deploy**. RunPod now builds the Docker image from GitHub, which takes about **10–20 minutes** the first time. You can watch the build log on the endpoint's page.
5. When the build finishes, copy the **Endpoint ID** from the endpoint page (e.g. `abc123xyz`).

---

## Step 6: Send your first request

The first request triggers a **cold start**: a GPU is assigned, the model downloads (or loads from the volume) and moves onto the GPU. Expect it to take **30–90 s**. After that, requests take a few seconds while the worker stays warm.

### From your Mac (Python)

```bash
pip install requests
export RUNPOD_API_KEY="rpa_..."          # from step 1
export RUNPOD_ENDPOINT_ID="abc123xyz"    # from step 5
cd /Volumes/work/dataset/runpod_serverless
python test_client.py "আসসালামু আলাইকুম! আমি আপনাকে কীভাবে সাহায্য করতে পারি?" Charon out.wav
open out.wav
```

### With curl

```bash
curl -s -X POST "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "আসসালামু আলাইকুম!", "voice": "Kore"}}' \
  | python3 -c 'import sys,json,base64; o=json.load(sys.stdin)["output"]; open("out.wav","wb").write(base64.b64decode(o["audio_base64"])); print(o["duration_sec"], "s")'
```

### Request format

```json
{
  "input": {
    "text": "বাংলা টেক্সট",
    "voice": "Charon",
    "num_step": 32,
    "speed": 1.0
  }
}
```

- `text` (required): the Bengali text to speak.
- `voice`: `Charon` (male) or `Kore` (female). Defaults to `Charon`.
- `num_step` (optional): generation steps, default 32. Try **16** for about 2× faster generation, and check that the quality is still acceptable.
- `speed` (optional): e.g. `0.9` is slower and `1.1` is faster.

### Response

```json
{
  "status": "COMPLETED",
  "output": {
    "audio_base64": "UklGR...",
    "format": "wav",
    "sample_rate": 24000,
    "duration_sec": 4.2,
    "generation_sec": 1.3,
    "voice": "Charon"
  }
}
```

The `audio_base64` field is a normal WAV file (24 kHz, 16-bit, mono) encoded as base64. Decode it and save it as `.wav`.

- **`/runsync` vs `/run`:** `/runsync` waits for the result, which is simplest. For long jobs, use `/run`, which returns a job `id` straight away. Then poll `GET /status/<id>` until `status` is `COMPLETED`. `test_client.py` handles both cases.

---

## Step 7: Keep costs low

- **Leave Active workers at 0.** You pay only while a worker is running, which includes its idle-timeout period.
- **Tune the idle timeout.** Short (5–30 s) means cheapest, but more cold starts. Long (60–300 s) means snappier during busy periods.
- **Cache repeated phrases in your app.** Greetings, "please hold" and goodbyes can be generated once and stored as WAV files. Only call the endpoint for new text.
- **Use `num_step: 16`** if it sounds good enough.
- **Check usage:** RunPod → Billing shows what the endpoint costs.
- **Always-warm, real-time response:** set Active workers to **1**. You'll pay for that worker 24/7, but there are no cold starts.

---

## Step 8: Updating the model later

When you retrain and push a new version to the same Hugging Face repo:

- **When workers pick it up:** new workers download the latest version automatically when they start. Workers that are already warm keep the old one until they shut down.
- **To switch immediately:** on the endpoint page, set Max workers to 0, wait until no workers are running, then set it back. You could also push a small commit to GitHub, which triggers a rebuild and a rollout.
- **If you changed `handler.py`,** push to GitHub and RunPod rebuilds the image.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails at `FROM pytorch/pytorch:2.8.0-...` | That image tag may have moved. Pick a current tag with CUDA 12.x from <https://hub.docker.com/r/pytorch/pytorch/tags> and keep `torch==2.8.0` in `requirements.txt`, or use a RunPod PyTorch 2.8 base image |
| `401` / `Repository Not Found` in the worker logs | `HF_TOKEN` is missing or wrong. Check the `hf_token` secret and the `{{ RUNPOD_SECRET_hf_token }}` environment variable, and that the token can read `sawon19/omnivoice-bengali` |
| Requests stay `IN_QUEUE` for a long time | No GPU is free in your selected tiers or region. Add more GPU tiers, or remove the network volume so any data centre can be used |
| Every request is slow (30 s+) | Workers are cold-starting each time. Raise the idle timeout, turn on FlashBoot, add the network volume, or keep 1 active worker |
| `unknown voice` error | Use `Charon` or `Kore`, or match whatever is in `VOICES` |
| `CUDA out of memory` | Very unlikely on 16 GB+. Split very long texts into smaller chunks |
| Worker logs | Endpoint page → **Workers / Logs**. The cold-start line reads `loaded sawon19/omnivoice-bengali with voices [...] in XXs` |
