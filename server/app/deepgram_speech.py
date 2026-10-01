"""Deepgram hosted speech-to-text (batch). Opt-in via SPATIAL_SPEECH_BACKEND=deepgram; the key comes only from the
environment / per-user server.env (config.py) and is never logged or echoed in errors."""
from __future__ import annotations

import json
import queue
import threading

import httpx

from app.config import settings

URL = "https://api.deepgram.com/v1/listen"
WS_URL = "wss://api.deepgram.com/v1/listen"


class SpeechError(Exception):
    pass


_http: httpx.Client | None = None


def _client() -> httpx.Client:
    """One kept-alive connection pool: a fresh client per call re-pays the TLS handshake (about a second from far away)."""
    global _http
    if _http is None:
        _http = httpx.Client(timeout=settings.speech_timeout)
    return _http


def available() -> bool:
    return bool(settings.deepgram_api_key)


def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    """Send the recorded clip (webm/opus, wav, ...: Deepgram detects the container) and return the same shape as
    the other backends. Raises SpeechError with a key-free message on any failure."""
    params = f"model={settings.deepgram_model}&smart_format=true&punctuate=true"
    params += f"&language={language}" if language else "&language=en"
    try:
        response = _client().post(
            f"{URL}?{params}", content=audio_bytes,
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


def stream_transcribe(chunks: queue.Queue, publish, state: dict | None = None) -> list[bytes]:
    """Live transcript: send 16 kHz mono PCM16 chunks (queue ends with None) over Deepgram's streaming socket and
    publish the stitched transcript (finalized segments + the current interim one). Returns the chunks it consumed.
    Raises SpeechError (key-free) on connect/stream failure; `state` exposes consumed/finished so the caller can
    continue with local windows without losing audio."""
    from websockets.sync.client import connect

    state = state if state is not None else {}
    consumed: list[bytes] = state.setdefault("consumed", [])
    state["finished"] = False
    params = (f"model={settings.deepgram_model}&encoding=linear16&sample_rate=16000&channels=1&language=en"
              "&interim_results=true&smart_format=true&punctuate=true")
    try:
        ws = connect(f"{WS_URL}?{params}", additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
                     open_timeout=settings.speech_timeout, max_size=2**22)
    except Exception as exc:
        raise SpeechError(f"network: {type(exc).__name__}") from None

    def sender() -> None:
        try:
            while True:
                chunk = chunks.get()
                if chunk is None:
                    state["finished"] = True
                    ws.send(json.dumps({"type": "CloseStream"}))
                    return
                consumed.append(chunk)
                ws.send(chunk)
        except Exception:  # the receive loop reports the failure
            return

    feeder = threading.Thread(target=sender, daemon=True, name="spatial-deepgram-send")
    feeder.start()
    committed = ""
    try:
        for message in ws:
            if isinstance(message, bytes):
                continue
            data = json.loads(message)
            if data.get("type") != "Results":
                continue
            alternatives = (data.get("channel") or {}).get("alternatives") or [{}]
            text = str(alternatives[0].get("transcript", "")).strip()
            if not text:
                continue
            final = bool(data.get("is_final"))
            shown = f"{committed} {text}".strip()
            if final:
                committed = shown
            publish({"type": "transcript", "text": shown, "final": final})
    except Exception as exc:
        raise SpeechError(f"stream: {type(exc).__name__}") from None
    finally:
        try:
            ws.close()
        except Exception:
            pass
        feeder.join(timeout=2)
    return consumed
