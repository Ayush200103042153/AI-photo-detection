import io
import os
from typing import Dict, Any

import requests
from huggingface_hub import InferenceClient
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



def ai_score_from_huggingface(
    image_bytes: bytes,
) -> Dict[str, Any]:
    """
    Second independent detector using Hugging Face Inference.

    Required Render environment variable:
      HF_TOKEN=hf_...

    Model:
      dima806/ai_vs_real_image_detection

    The model returns class probabilities for REAL vs FAKE/AI.
    We normalize those labels into one 0..1 AI probability.
    """
    token = os.getenv("HF_TOKEN")

    if not token:
        raise RuntimeError(
            "Second AI detector is not configured. Add HF_TOKEN "
            "to your Render environment variables."
        )

    client = InferenceClient(
        provider="hf-inference",
        api_key=token,
    )

    try:
        output = client.image_classification(
            image_bytes,
            model="dima806/ai_vs_real_image_detection",
        )
    except Exception as exc:
        raise RuntimeError(
            f"Hugging Face detector failed: {exc}"
        ) from exc

    ai_probability = None
    real_probability = None
    raw_scores = {}

    for item in output:
        if isinstance(item, dict):
            label = str(item.get("label", "")).strip().lower()
            score = float(item.get("score", 0.0))
        else:
            label = str(getattr(item, "label", "")).strip().lower()
            score = float(getattr(item, "score", 0.0))

        raw_scores[label] = score

        if any(word in label for word in ("fake", "ai", "artificial", "generated")):
            ai_probability = score if ai_probability is None else max(ai_probability, score)

        if any(word in label for word in ("real", "human", "authentic")):
            real_probability = score if real_probability is None else max(real_probability, score)

    if ai_probability is None and real_probability is not None:
        ai_probability = 1.0 - real_probability

    if ai_probability is None:
        raise RuntimeError(
            f"Hugging Face detector returned labels that could not be mapped: "
            f"{list(raw_scores.keys())}"
        )

    ai_probability = min(max(float(ai_probability), 0.0), 1.0)

    return {
        "probability": ai_probability,
        "source": "Hugging Face dima806/ai_vs_real_image_detection",
        "raw_scores": raw_scores,
    }


def combine_detector_scores(
    sightengine_probability: float,
    huggingface_probability: float,
) -> float:
    """
    Equal-weight ensemble.

    We do NOT remap 0.1% to an invented middle value. The middle scores come
    naturally when two independent models disagree or have different confidence.
    """
    combined = (sightengine_probability + huggingface_probability) / 2.0
    return min(max(combined, 0.0), 1.0)

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
        sightengine = ai_score_from_sightengine(
            image_bytes,
            file.filename or "upload.jpg",
            content_type,
        )
        huggingface = ai_score_from_huggingface(
            image_bytes,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    sightengine_probability = float(sightengine["probability"])
    huggingface_probability = float(huggingface["probability"])

    probability = combine_detector_scores(
        sightengine_probability,
        huggingface_probability,
    )

    pct = probability * 100.0
    sightengine_pct = sightengine_probability * 100.0
    huggingface_pct = huggingface_probability * 100.0
    disagreement = abs(sightengine_probability - huggingface_probability)

    if probability >= 1.0:
        explanation = (
            f"Combined AI score: {pct:.1f}%. Both detection signals produced "
            "maximum AI confidence."
        )
    elif probability >= 0.40:
        explanation = (
            f"Combined AI score: {pct:.1f}%. This is the average of two "
            "independent AI-image detectors, so the score can represent "
            "uncertain and in-between cases instead of forcing a binary answer."
        )
    else:
        explanation = (
            f"Combined AI score: {pct:.1f}%. The combined result is below the "
            "40% threshold, so this site labels the image as legit."
        )

    explanation += (
        f" Detector signals: Sightengine {sightengine_pct:.1f}% AI, "
        f"Hugging Face {huggingface_pct:.1f}% AI."
    )

    if disagreement >= 0.40:
        explanation += (
            " The detectors disagree strongly on this image, so this result "
            "should be treated as uncertain."
        )

    likely_generator = sightengine.get("likely_generator")
    likely_generator_score = float(
        sightengine.get("likely_generator_score") or 0
    )


    generator_notes = []

    if likely_generator and likely_generator_score >= 0.40:
        generator_notes.append(
            f"{likely_generator.replace('_', ' ').title()} "
            f"{likely_generator_score * 100:.1f}%"
        )


    if generator_notes:
        explanation += (
            " Possible generator signals: " + ", ".join(generator_notes) + "."
        )

    return {
        "verdict": verdict_for(probability),
        "ai_probability": probability,
        "ai_percentage": round(probability * 100.0, 3),
        "explanation": explanation,
        "detectors": {
            "sightengine_ai_percentage": round(
                sightengine_probability * 100.0, 3
            ),
            "huggingface_ai_percentage": round(
                huggingface_probability * 100.0, 3
            ),
        },
        "stores_upload": False,
    }
