# Orbital Verify — AI Image Detector Prototype

A no-database, one-image-at-a-time web app with an outer-space theme.

## Features

- Image upload by click or drag/drop
- Video input rejected with: "Video input is not available right now."
- AI-generation likelihood score
- Result bands:
  - 95%+ => "AI generated — high confidence"
  - 50–94% => "Might be AI generated"
  - Below 50% => "Likely not AI generated"
- Optional visual-similarity / reverse-image provider hook
- No upload database
- Back / "Scan another image" resets to the homepage
- Footer: "Build and designed by Ayush Patel"

## Important limitation

No current AI-image detector can reliably prove image provenance with 100% certainty.
This app therefore reports a probability/confidence result rather than claiming absolute proof.

Also, no normal application can literally compare an uploaded image against "the whole open internet."
For production, connect a licensed web-visual-search provider such as Google Cloud Vision Web Detection,
TinEye API, or another reverse-image search service.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000

## Configure an AI detector

Set environment variables:

```bash
export HF_API_TOKEN="your_token"
export HF_MODEL_ID="your_detector_model_id"
```

The selected model must be an image classifier that returns labels distinguishing AI/synthetic images from real images.
If its labels differ, update `AI_LABELS` and `REAL_LABELS` in `main.py`.

Without these variables, the app deliberately returns a neutral 50% demo score.

## Add web similarity search

Implement `web_similar_images()` in `main.py` using the provider you choose.
Return a list shaped like:

```python
[
  {
    "title": "Example",
    "thumbnail": "https://...",
    "image_url": "https://...",
    "source_url": "https://...",
    "source": "example.com"
  }
]
```

## Privacy

The included app does not use a database. Uploaded bytes live only for the lifetime of the request unless you add external APIs.
Note: any external AI or visual-search API you connect may have its own data-retention policy.
