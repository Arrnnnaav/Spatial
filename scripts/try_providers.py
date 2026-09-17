"""Live smoke test: which providers, OCR and speech engines actually work with the current .env.

python scripts/try_providers.py            # against a running server on SPATIAL_PORT (default 8787)
python scripts/try_providers.py --direct   # call providers in-process, no server needed
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import httpx

QUESTION = "Why is there a minus sign in this update rule?"
ANCHORS = [
    {
        "id": "eq",
        "type": "p",
        "text": "θ_new = θ − η ∇L(θ)",
        "bbox": {"x": 20, "y": 30, "width": 560, "height": 40},
    }
]


def sample_crop() -> str:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (620, 160), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        font = ImageFont.load_default()
    draw.text(
        (20, 30), "theta_new = theta - eta * grad L(theta)", fill="black", font=font
    )
    draw.text((20, 90), "eta is the learning rate", fill="black", font=font)
    draw.ellipse((5, 5, 610, 150), outline=(255, 61, 127), width=5)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def payload(provider: str | None, crop: str | None) -> dict:
    return {
        "question": QUESTION,
        "provider": provider,
        "image_data": crop,
        "anchors": ANCHORS,
        "marks": [{"type": "circle", "x": 10, "y": 10, "width": 600, "height": 140}],
        "canvas": {"width": 1280, "height": 720},
        "page": {"title": "Gradient descent notes", "surface": "web"},
    }


def via_server(base: str) -> None:
    health = httpx.get(f"{base}/api/health", timeout=30).json()
    print("server:", base)
    print("audio:", json.dumps(health["audio"]))
    crop = sample_crop()
    for item in health["providers"]:
        if not item["configured"]:
            print(f"- {item['name']:<10} not configured")
            continue
        started = time.time()
        try:
            response = httpx.post(
                f"{base}/api/ask", json=payload(item["name"], crop), timeout=300
            )
            body = response.json()
            print(
                f"- {item['name']:<10} {response.status_code} {time.time() - started:5.1f}s  {body.get('status')} model={body.get('model')} vision={body.get('vision')} ocr={body.get('ocr')}"
            )
            print(
                "    ",
                (body.get("answer") or body.get("detail", ""))[:160].replace("\n", " "),
            )
            if body.get("errors"):
                print("     errors:", json.dumps(body["errors"])[:300])
        except Exception as exc:
            print(f"- {item['name']:<10} failed: {exc}")
    started = time.time()
    tts = httpx.post(
        f"{base}/api/tts",
        json={"text": "The minus sign moves against the gradient."},
        timeout=600,
    )
    if tts.status_code == 200:
        print(
            f"tts: 200 {time.time() - started:5.1f}s -> {tts.headers.get('x-tts-seconds', '?')}s of audio"
        )
        started = time.time()
        stt = httpx.post(
            f"{base}/api/stt",
            files={"audio": ("tts.wav", tts.content, "audio/wav")},
            timeout=600,
        )
        print(
            f"stt: {stt.status_code} {time.time() - started:5.1f}s",
            stt.json() if stt.status_code == 200 else stt.text[:120],
        )
    else:
        print(f"tts: {tts.status_code} {tts.text[:160]}")


def direct() -> None:
    from app.config import settings
    from app.ocr import ocr_image
    from app.providers import answer

    crop = sample_crop()
    print("OCR:", ocr_image(crop).replace("\n", " | ") or "(rapidocr not installed)")
    for name, config in settings.providers.items():
        if not config.configured:
            print(f"- {name:<10} not configured")
            continue
        started = time.time()
        text, meta = answer(
            QUESTION,
            {"title": "Gradient descent notes"},
            ANCHORS,
            crop,
            provider_name=name,
        )
        print(
            f"- {name:<10} {time.time() - started:5.1f}s {meta.get('status')} model={meta.get('model')} vision={meta.get('vision')} ocr={meta.get('ocr')}"
        )
        print("    ", text[:160].replace("\n", " "))
        if meta.get("errors"):
            print("     errors:", json.dumps(meta["errors"])[:300])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true")
    parser.add_argument(
        "--base", default=f"http://127.0.0.1:{os.environ.get('SPATIAL_PORT', '8787')}"
    )
    args = parser.parse_args()
    direct() if args.direct else via_server(args.base)
