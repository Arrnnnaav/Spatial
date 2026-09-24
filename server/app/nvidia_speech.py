"""NVIDIA hosted speech (build.nvidia.com, Riva gRPC on grpc.nvcf.nvidia.com): Parakeet / Whisper ASR, Magpie TTS.
Measured 2026-09-24 with the NVIDIA key: ASR ~1.0 s and TTS ~1.3 s for a short sentence, no model load — versus
~5 s / ~2 s warm and 25-30 s cold for the local CPU models, which stay as the fallback (app/audio.py).

Every call runs under a hard time budget and retries "busy" gRPC errors like the answer providers do."""

from __future__ import annotations

import concurrent.futures
import io
import re
import time
import wave
from functools import lru_cache

from app.config import settings

ENDPOINT = "grpc.nvcf.nvidia.com:443"
TTS_SAMPLE_RATE = 22050
TTS_MAX_CHARS = 1500  # hosted TTS rejects > 2000 characters per request
_BUSY_CODES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED", "ABORTED", "INTERNAL"}
_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="spatial-nv-speech"
)


class SpeechError(Exception):
    pass


def available() -> bool:
    from importlib.util import find_spec

    key = settings.providers.get("nvidia")
    return bool(key and key.api_key) and find_spec("riva") is not None


def _api_key() -> str:
    return settings.providers["nvidia"].api_key


@lru_cache(maxsize=8)
def _service(kind: str, function_id: str):
    """One kept-alive TLS channel per hosted function (the first call pays the handshake)."""
    import riva.client

    auth = riva.client.Auth(
        None,
        True,
        ENDPOINT,
        [["function-id", function_id], ["authorization", "Bearer " + _api_key()]],
    )
    return (
        riva.client.ASRService(auth)
        if kind == "asr"
        else riva.client.SpeechSynthesisService(auth)
    )


def warm() -> None:
    """First use off the request path: the TLS channel opens and the hosted function wakes only on a real call
    (measured 6 s TTS / 22 s STT cold vs 0.7 s / 0.5 s warm), and the webm decoder import is slow. Never raises."""
    try:
        from faster_whisper.audio import decode_audio  # noqa: F401  (heavy import, used for webm/opus)
    except Exception:
        pass
    try:
        synthesize("Ready.")
        transcribe(pcm16_wav(b"\x00\x00" * 8000, 16000))
    except Exception:
        pass


def _code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    try:
        return code().name if callable(code) else ""
    except Exception:
        return ""


def _call(fn, *args):
    """Hard time budget + up to `provider_attempts` tries on busy errors; auth/bad-request errors fail at once."""
    deadline = time.monotonic() + settings.speech_timeout
    last = None
    for attempt in range(settings.provider_attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        future = _pool.submit(fn, *args)
        try:
            return future.result(timeout=remaining)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise SpeechError("timeout") from None
        except Exception as exc:
            last = exc
            code = _code(exc)
            if code not in _BUSY_CODES or attempt == settings.provider_attempts - 1:
                raise SpeechError(
                    f"{code or type(exc).__name__}: {str(exc)[:160]}"
                ) from exc
            time.sleep(0.5 * (attempt + 1))
    raise SpeechError(f"busy: {str(last)[:160]}")


def pcm16_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def to_wav16k(audio_bytes: bytes) -> bytes:
    """MediaRecorder gives webm/opus; hosted ASR wants PCM. WAV input passes through untouched."""
    if audio_bytes[:4] == b"RIFF":
        return audio_bytes
    import numpy as np
    from faster_whisper.audio import (
        decode_audio,
    )  # PyAV decode only; no model is loaded

    samples = decode_audio(io.BytesIO(audio_bytes), sampling_rate=16000)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return pcm16_wav(pcm, 16000)


def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    """English (or unspecified) -> Parakeet; any other language -> Whisper large-v3 (multilingual)."""
    import riva.client

    english = not language or language.lower().startswith("en")
    function_id = (
        settings.nvidia_asr_function
        if english
        else settings.nvidia_asr_multilingual_function
    )
    model = "parakeet-tdt-0.6b-v2" if english else "whisper-large-v3"
    wav = to_wav16k(audio_bytes)
    config = riva.client.RecognitionConfig(
        language_code="en-US" if english else language,
        max_alternatives=1,
        enable_automatic_punctuation=True,
    )
    response = _call(_service("asr", function_id).offline_recognize, wav, config)
    text = " ".join(
        r.alternatives[0].transcript.strip() for r in response.results if r.alternatives
    ).strip()
    with wave.open(io.BytesIO(wav)) as w:
        duration = w.getnframes() / float(w.getframerate() or 1)
    return {
        "status": "ok",
        "text": text,
        "language": "en" if english else language,
        "duration": round(duration, 2),
        "model": model,
        "backend": "nvidia",
    }


def _chunks(text: str) -> list[str]:
    """Sentence-aligned pieces under the hosted limit."""
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(sentence) > TTS_MAX_CHARS:
            parts.append(sentence[:TTS_MAX_CHARS])
            sentence = sentence[TTS_MAX_CHARS:]
        if current and len(current) + 1 + len(sentence) > TTS_MAX_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def synthesize(text: str, voice: str | None = None) -> tuple[bytes, dict]:
    # Voice names from the local engine (e.g. "alba") mean nothing to Magpie: only pass Magpie voices through.
    voice = voice if voice and voice.startswith("Magpie") else settings.nvidia_tts_voice
    service = _service("tts", settings.nvidia_tts_function)
    deadline = time.monotonic() + 2 * settings.speech_timeout  # whole request, however many chunks
    pieces = []
    for chunk in _chunks(text[:6000]):
        if time.monotonic() > deadline:
            raise SpeechError("timeout")
        pieces.append(_call(lambda piece: service.synthesize(piece, voice_name=voice, language_code="en-US",
                                                             sample_rate_hz=TTS_SAMPLE_RATE), chunk).audio)
    pcm = b"".join(pieces)
    return pcm16_wav(pcm, TTS_SAMPLE_RATE), {
        "status": "ok",
        "sample_rate": TTS_SAMPLE_RATE,
        "voice": voice,
        "backend": "nvidia",
        "seconds": round(len(pcm) / 2 / TTS_SAMPLE_RATE, 2),
    }
