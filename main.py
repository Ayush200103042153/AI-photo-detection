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

def ai_score_from_sightengine(
    image_bytes: bytes,
    filename: str,
    content_type: str
) -> Dict[str, Any]:
    """
    Uses Sightengine's AI-generated image detection endpoint.

    Required environment variables:
      SIGHTENGINE_API_USER=...
      SIGHTENGINE_API_SECRET=...

    The API returns type.ai_generated as a confidence value from 0 to 1.
    There is intentionally NO fake 50% fallback. If credentials are missing
    or the detector fails, the request returns an error instead of inventing
    a score.
    """
    api_user = os.getenv("SIGHTENGINE_API_USER")
    api_secret = os.getenv("SIGHTENGINE_API_SECRET")

    if not api_user or not api_secret:
        raise RuntimeError(
            "AI detector is not configured. Add SIGHTENGINE_API_USER and "
            "SIGHTENGINE_API_SECRET to your environment variables."
        )

    files = {
        "media": (
            filename or "upload.jpg",
            image_bytes,
            content_type or "application/octet-stream",
        )
    }
    data = {
        "models": "genai",
        "api_user": api_user,
        "api_secret": api_secret,
    }

    try:
        response = requests.post(
            "https://api.sightengine.com/1.0/check.json",
            files=files,
            data=data,
            timeout=45,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"AI detector connection failed: {exc}") from exc

    try:
        output = response.json()
    except ValueError as exc:
        raise RuntimeError("AI detector returned an invalid response.") from exc

    if not response.ok or output.get("status") != "success":
        error = output.get("error", {})
        message = (
            error.get("message")
            if isinstance(error, dict)
            else str(error or "")
        )
        raise RuntimeError(
            f"AI detector error: {message or f'HTTP {response.status_code}'}"
        )

    try:
        probability = float(output["type"]["ai_generated"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "AI detector response did not contain an ai_generated score."
        ) from exc

    probability = min(max(probability, 0.0), 1.0)

    generator_scores = output.get("type", {}).get("ai_generators", {}) or {}
    likely_generator = None
    likely_generator_score = 0.0

    for name, raw_score in generator_scores.items():
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if score > likely_generator_score:
            likely_generator = name
            likely_generator_score = score

    return {
        "probability": probability,
        "source": "Sightengine genai",
        "likely_generator": likely_generator,
        "likely_generator_score": likely_generator_score,
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
    """
    Thresholds use the detector's RAW probability, not a rounded percentage:
      exactly 1.0      -> AI generated
      0.40 to < 1.0   -> Might be AI generated
      below 0.40      -> Image is legit

    The percentage is a detector confidence score, not mathematical proof.
    """
    if prob >= 1.0:
        return "AI generated"

    if prob >= 0.40:
        return "Might be AI generated"

    return "Image is legit"


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
        detector = ai_score_from_sightengine(
            image_bytes,
            file.filename or "upload.jpg",
            content_type,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    probability = float(detector["probability"])

    # The starter web_similar_images() function is only a placeholder until you
    # connect a real reverse-image / web-visual-search provider.
    #
    # Set WEB_IMAGE_SEARCH_ENABLED=true only after implementing that provider.
    web_search_ran = os.getenv("WEB_IMAGE_SEARCH_ENABLED", "false").lower() == "true"

    matches = []
    if web_search_ran:
        matches = web_similar_images(image_bytes, file.filename or "upload")

    # Preserve the detector's real score. Round only for display.
    pct = probability * 100.0
    display_pct = f"{pct:.1f}%"

    if probability >= 1.0:
        explanation = (
            f"AI detector score: {display_pct}. The detector returned its maximum "
            "AI-generation confidence."
        )
    elif probability >= 0.40:
        explanation = (
            f"AI detector score: {display_pct}. The image is at or above the 40% "
            "threshold, so it is flagged as possibly AI generated."
        )
    else:
        explanation = (
            f"AI detector score: {display_pct}. The image is below the 40% threshold, "
            "so this site labels it as legit."
        )

    likely_generator = detector.get("likely_generator")
    likely_generator_score = float(detector.get("likely_generator_score") or 0)

    if likely_generator and likely_generator_score >= 0.40:
        pretty_name = likely_generator.replace("_", " ").title()
        explanation += (
            f" Strongest generator signal: {pretty_name} "
            f"({likely_generator_score * 100:.1f}%)."
        )

    return {
        "verdict": verdict_for(probability),
        "ai_probability": probability,
        "ai_percentage": round(probability * 100.0, 3),
        "explanation": explanation,
        "detector_source": detector.get("source"),
        "similar_images": matches[:12],
        "web_search_enabled": web_search_ran,
        "stores_upload": False
    }
