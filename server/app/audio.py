"""CPU speech: faster-whisper for speech-to-text, Kyutai pocket-tts for text-to-speech.
Both lazy-loaded and optional; the endpoints report 'unavailable' instead of failing the server."""
from __future__ import annotations

import gc
import io
import threading
import time
from functools import lru_cache

from app.config import settings

_lock = threading.Lock()
_last_used = 0.0


def _touch() -> None:
    global _last_used
    _last_used = time.time()
    _start_unloader()


_unloader_started = False


def _start_unloader() -> None:
    """Background thread that drops the whisper/TTS models after an idle period to give RAM back."""
    global _unloader_started
    if _unloader_started or settings.audio_idle_unload_seconds <= 0:
        return
    _unloader_started = True

    def run() -> None:
        while True:
            time.sleep(30)
            if _last_used and time.time() - _last_used > settings.audio_idle_unload_seconds and (_whisper.cache_info().currsize or _tts.cache_info().currsize):
                with _lock:
                    _whisper.cache_clear(); _voice.cache_clear(); _tts.cache_clear()
                    gc.collect()
    threading.Thread(target=run, name="spatial-audio-unloader", daemon=True).start()


def _prepare_downloads() -> None:
    if settings.force_ipv4:
        import urllib3.util.connection as connection
        connection.HAS_IPV6 = False


@lru_cache(maxsize=1)
def _whisper():
    _prepare_downloads()
    from faster_whisper import WhisperModel
    return WhisperModel(_cached_whisper_dir(settings.stt_model), device=settings.stt_device, compute_type="int8" if settings.stt_device == "cpu" else "float16")


def _cached_whisper_dir(size: str) -> str:
    """Use an already-cached Systran/faster-whisper-<size> snapshot directly so a flaky network never blocks STT."""
    from pathlib import Path
    hub = Path.home() / ".cache" / "huggingface" / "hub" / f"models--Systran--faster-whisper-{size}" / "snapshots"
    for snapshot in sorted(hub.glob("*"), reverse=True) if hub.exists() else []:
        if (snapshot / "model.bin").exists():
            return str(snapshot)
    return size


def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    _touch()
    try:
        model = _whisper()
    except Exception as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {str(exc)[:160]}", "text": ""}
    for attempt in (1, 2):
        try:
            with _lock:
                segments, info = model.transcribe(io.BytesIO(audio_bytes), language=language, beam_size=1, vad_filter=True)
                text = " ".join(segment.text.strip() for segment in segments).strip()
            break
        except RuntimeError as exc:  # mkl_malloc under memory pressure: free what we can and retry once
            if attempt == 2 or "alloc" not in str(exc).lower():
                return {"status": "unavailable", "error": f"RuntimeError: {str(exc)[:160]} (low memory? close other models)", "text": ""}
            import gc
            gc.collect()
    return {"status": "ok", "text": text, "language": info.language, "duration": round(info.duration, 2), "model": settings.stt_model}


@lru_cache(maxsize=1)
def _tts():
    _prepare_downloads()
    from pocket_tts import TTSModel
    return TTSModel.load_model()


@lru_cache(maxsize=8)
def _voice(name: str):
    return _tts().get_state_for_audio_prompt(name)


def synthesize(text: str, voice: str | None = None) -> tuple[bytes | None, dict]:
    if not settings.tts_enabled:
        return None, {"status": "disabled"}
    _touch()
    try:
        model = _tts()
        state = _voice(voice or settings.tts_voice)
    except Exception as exc:
        return None, {"status": "unavailable", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    import numpy as np
    with _lock:
        audio = model.generate_audio(state, text[:2000])
    pcm = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    return _wav_bytes(pcm, model.sample_rate), {"status": "ok", "sample_rate": model.sample_rate, "voice": voice or settings.tts_voice, "seconds": round(len(pcm) / model.sample_rate, 2)}


def _wav_bytes(pcm, sample_rate: int) -> bytes:
    import struct
    import wave
    import numpy as np
    clipped = np.clip(np.asarray(pcm, dtype=np.float32), -1.0, 1.0)
    data = (clipped * 32767).astype("<i2").tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sample_rate); wav.writeframes(data)
    return buffer.getvalue()


def audio_status() -> dict:
    from importlib.util import find_spec
    return {"stt": {"model": settings.stt_model, "device": settings.stt_device, "installed": find_spec("faster_whisper") is not None},
            "tts": {"voice": settings.tts_voice, "enabled": settings.tts_enabled, "installed": find_spec("pocket_tts") is not None}}
