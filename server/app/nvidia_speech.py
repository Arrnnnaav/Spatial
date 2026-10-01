"""NVIDIA hosted speech (build.nvidia.com, Riva gRPC on grpc.nvcf.nvidia.com): Parakeet / Whisper ASR, Magpie TTS.
Measured 2026-09-24 with the NVIDIA key: ASR ~1.0 s and TTS ~1.3 s for a short sentence, no model load — versus
~5 s / ~2 s warm and 25-30 s cold for the local CPU models, which stay as the fallback (app/audio.py).

Every call runs under a hard time budget and retries "busy" gRPC errors like the answer providers do."""

from __future__ import annotations

import concurrent.futures
import io
import queue
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


def stream_transcribe(chunks: queue.Queue, publish) -> None:
    """Consume 16 kHz mono PCM and publish hosted or local partial transcripts.

    `chunks` is terminated by None. Kept synchronous because the Riva client exposes a
    blocking gRPC iterator; the WebSocket route runs this on a worker thread.
    """
    from app.audio import backend as selected_backend
    from app.audio import cloud_speech_enabled

    if cloud_speech_enabled():
        from app import deepgram_speech

        state: dict = {}
        try:
            deepgram_speech.stream_transcribe(chunks, publish, state)
            return
        except Exception:  # connect/auth/network: continue with bounded local windows, keeping the audio so far
            _local_stream_transcribe(chunks, publish, state.get("consumed", ()), state.get("finished", False))
            return
    if selected_backend() != "nvidia":
        _local_stream_transcribe(chunks, publish)
        return

    consumed = []
    stream_finished = False

    def audio_chunks():
        nonlocal stream_finished
        while True:
            chunk = chunks.get()
            if chunk is None:
                stream_finished = True
                return
            consumed.append(chunk)
            yield chunk

    try:
        import riva.client

        config = riva.client.RecognitionConfig(
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            sample_rate_hertz=16000,
            audio_channel_count=1,
            language_code="en-US",
            max_alternatives=1,
            enable_automatic_punctuation=True,
        )
        streaming = riva.client.StreamingRecognitionConfig(config=config, interim_results=True)
        service = _service("asr", settings.nvidia_asr_function)
        requests = riva.client.asr.streaming_request_generator(audio_chunks(), streaming)
        responses = service.stub.StreamingRecognize(
            requests, metadata=service.auth.get_auth_metadata(), timeout=75
        )
        for response in responses:
            results = response.results
            if results and results[0].alternatives:
                publish({"type": "transcript", "text": results[0].alternatives[0].transcript.strip(),
                         "final": bool(results[0].is_final)})
    except Exception:
        # NVCF's configured Parakeet function currently exposes offline recognition only. Transcribe
        # bounded 3-second windows with 0.5-second overlap instead of retrying the growing recording.
        _local_stream_transcribe(chunks, publish, consumed, stream_finished)


def _local_stream_transcribe(chunks: queue.Queue, publish, consumed=(), stream_finished=False) -> None:
    """Transcribe bounded overlapping windows locally and publish the stitched preview."""
    from app.audio import transcribe as offline_transcribe

    pending = bytearray(b"".join(consumed))
    committed = ""

    def flush(size: int):
        nonlocal committed, pending
        raw = bytes(pending[:size])
        result = offline_transcribe(pcm16_wav(raw, 16000), "en")
        pending = pending[size - 8000 :] if size > 8000 else bytearray()  # 0.5 s at 16 kHz PCM16
        words = (result.get("text") or "").split()
        previous = committed.split()
        overlap = 0
        for count in range(min(8, len(previous), len(words)), 0, -1):
            norm = lambda word: re.sub(r"\W", "", word).casefold()
            if [norm(x) for x in previous[-count:]] == [norm(x) for x in words[:count]]:
                overlap = count
                break
        committed = " ".join([committed, *words[overlap:]]).strip()
        if committed:
            publish({"type": "transcript", "text": committed, "final": False})

    while True:
        while len(pending) >= 96000:  # 3 seconds at 16 kHz PCM16 mono
            flush(96000)
        if stream_finished:
            if len(pending) >= 32000:
                flush(len(pending))
            return
        chunk = chunks.get()
        if chunk is None:
            if len(pending) >= 32000:  # skip sub-second tail noise
                flush(len(pending))
            return
        pending.extend(chunk)


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
