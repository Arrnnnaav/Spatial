"""Deepgram hosted speech-to-text (batch). Opt-in via SPATIAL_SPEECH_BACKEND=deepgram; the key comes only from the
environment / per-user server.env (config.py) and is never logged or echoed in errors."""
from __future__ import annotations

import httpx

from app.config import settings

URL = "https://api.deepgram.com/v1/listen"


class SpeechError(Exception):
    pass


def available() -> bool:
    return bool(settings.deepgram_api_key)


def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    """Send the recorded clip (webm/opus, wav, ...: Deepgram detects the container) and return the same shape as
    the other backends. Raises SpeechError with a key-free message on any failure."""
    params = f"model={settings.deepgram_model}&smart_format=true&punctuate=true"
    params += f"&language={language}" if language else "&language=en"
    try:
        response = httpx.post(
            f"{URL}?{params}", content=audio_bytes, timeout=settings.speech_timeout,
            headers={"Authorization": f"Token {settings.deepgram_api_key}", "Content-Type": "application/octet-stream"},
        )
    except httpx.HTTPError as exc:
        raise SpeechError(f"network: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise SpeechError(f"http {response.status_code}")
    try:
        data = response.json()
        text = data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        duration = float(data.get("metadata", {}).get("duration", 0) or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        raise SpeechError("unexpected response") from None
    return {"status": "ok", "text": text, "language": language or "en", "duration": round(duration, 2),
            "model": settings.deepgram_model, "backend": "deepgram"}
