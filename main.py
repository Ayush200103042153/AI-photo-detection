import io
import os
from typing import List, Dict, Any

import requests
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Orbital Verify")

app.mount("/static", StaticFiles(directory="static"), name="static")

MAX_BYTES = 12 * 1024 * 1024

@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

def ai_score_from_huggingface(image_bytes: bytes) -> Dict[str, Any]:
    """
    Uses Hugging Face Inference API if configured.

    Set:
      HF_API_TOKEN=...
      HF_MODEL_ID=<an image-classification model that distinguishes AI vs real>

    IMPORTANT:
    Different models use different label names. Adjust AI_LABELS / REAL_LABELS
    below to match your chosen detector model.
    """
    token = os.getenv("HF_API_TOKEN")
    model_id = os.getenv("HF_MODEL_ID")

    if not token or not model_id:
        # Development fallback only. It deliberately returns an uncertain result
        # instead of pretending to detect AI without a model.
        return {
            "probability": 0.50,
            "source": "fallback",
            "note": "No AI detector model is configured, so this is a neutral demo score."
        }

    url = f"https://api-inference.huggingface.co/models/{model_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(url, headers=headers, data=image_bytes, timeout=45)
    if not r.ok:
        raise RuntimeError(f"Detector API error: {r.status_code}")

    output = r.json()
    if isinstance(output, list) and output and isinstance(output[0], list):
        output = output[0]

    AI_LABELS = {"ai", "artificial", "generated", "fake", "synthetic"}
    REAL_LABELS = {"real", "human", "photo", "natural"}

    ai_prob = 0.0
    real_prob = 0.0

    for item in output if isinstance(output, list) else []:
        label = str(item.get("label", "")).lower()
        score = float(item.get("score", 0))
        if any(k in label for k in AI_LABELS):
            ai_prob = max(ai_prob, score)
        if any(k in label for k in REAL_LABELS):
            real_prob = max(real_prob, score)

    if ai_prob == 0 and real_prob > 0:
        ai_prob = max(0.0, 1.0 - real_prob)
    if ai_prob == 0 and real_prob == 0:
        raise RuntimeError("Could not map model labels. Adjust AI_LABELS/REAL_LABELS.")

    return {
        "probability": min(max(ai_prob, 0.0), 1.0),
        "source": model_id,
        "note": "Probability is produced by the configured image-classification model."
    }

def web_similar_images(image_bytes: bytes, filename: str) -> List[Dict[str, str]]:
    """
    Optional reverse/similar-image search hook.

    This starter project leaves the provider pluggable because 'search the whole
    internet' is not realistically possible from a normal app, and providers have
    different contracts.

    Recommended production options:
    - Google Cloud Vision Web Detection
    - TinEye API
    - a licensed visual-search provider

    Implement one provider here and return:
    [
      {
        "title": "...",
        "thumbnail": "https://...",
        "image_url": "https://...",
        "source_url": "https://...",
        "source": "..."
      }
    ]
    """
    return []

def verdict_for(prob: float) -> str:
    # Never call this 100% proof. Detector scores are probabilistic.
    if prob >= 0.95:
        return "AI generated — high confidence"
    if prob >= 0.50:
        return "Might be AI generated"
    return "Likely not AI generated"

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    content_type = file.content_type or ""

    if content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Video input is not available right now.")
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Please upload an image file.")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 12 MB limit.")

    try:
        Image.open(io.BytesIO(image_bytes)).verify()
    except Exception:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image.")

    try:
        detector = ai_score_from_huggingface(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    probability = float(detector["probability"])
    matches = web_similar_images(image_bytes, file.filename or "upload")

    return {
        "verdict": verdict_for(probability),
        "ai_probability": probability,
        "explanation": (
            f"Detector score: {round(probability * 100)}%. "
            f"{detector.get('note', '')} "
            "Treat this as evidence, not absolute proof of how the image was created."
        ),
        "similar_images": matches[:12],
        "web_search_enabled": bool(matches),
        "stores_upload": False
    }
