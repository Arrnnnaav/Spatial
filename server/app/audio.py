"""Speech in/out. Primary: NVIDIA hosted models (app/nvidia_speech.py, ~1 s, no model load). Fallback: local CPU
faster-whisper (STT) and Kyutai pocket-tts (TTS), lazy-loaded and optional; the endpoints report 'unavailable'
instead of failing the server. `SPATIAL_SPEECH_BACKEND=auto|nvidia|local|deepgram` (deepgram is opt-in)."""
from __future__ import annotations

import gc
import sys
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
    return WhisperModel(
        _cached_whisper_dir(settings.stt_model),
        device=settings.stt_device,
        compute_type="int8" if settings.stt_device == "cpu" else "float16",
        cpu_threads=2 if settings.stt_device == "cpu" else 0,
        num_workers=1,
    )


def _cached_whisper_dir(size: str) -> str:
    """Use an already-cached Systran/faster-whisper-<size> snapshot directly so a flaky network never blocks STT."""
    from pathlib import Path
    hub = Path.home() / ".cache" / "huggingface" / "hub" / f"models--Systran--faster-whisper-{size}" / "snapshots"
    for snapshot in sorted(hub.glob("*"), reverse=True) if hub.exists() else []:
        if (snapshot / "model.bin").exists():
            return str(snapshot)
    return size


def _local_transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
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
        except Exception as exc:  # bad language code, undecodable audio, ...
            return {"status": "unavailable", "error": type(exc).__name__, "text": ""}
    return {"status": "ok", "text": text, "language": info.language, "duration": round(info.duration, 2), "model": settings.stt_model, "backend": "local"}


@lru_cache(maxsize=1)
def _tts():
    _prepare_downloads()
    from pocket_tts import TTSModel
    return TTSModel.load_model()


@lru_cache(maxsize=8)
def _voice(name: str):
    return _tts().get_state_for_audio_prompt(name)


def _local_synthesize(text: str, voice: str | None = None) -> tuple[bytes | None, dict]:
    if not settings.tts_enabled:
        return None, {"status": "disabled"}
    _touch()
    try:
        model = _tts()
        state = _voice(voice or settings.tts_voice)
    except Exception as exc:
        if sys.platform == "win32":
            try:
                wav = _windows_synthesize(text)
                import wave
                with wave.open(io.BytesIO(wav), "rb") as audio_file:
                    seconds = round(audio_file.getnframes() / audio_file.getframerate(), 2)
                return wav, {"status": "ok", "voice": "system", "backend": "windows-sapi", "seconds": seconds}
            except Exception:
                pass
        return None, {"status": "unavailable", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    import numpy as np
    with _lock:
        audio = model.generate_audio(state, text[:2000])
    pcm = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    return _wav_bytes(pcm, model.sample_rate), {"status": "ok", "sample_rate": model.sample_rate, "voice": voice or settings.tts_voice, "seconds": round(len(pcm) / model.sample_rate, 2), "backend": "local"}


def _windows_synthesize(text: str) -> bytes:
    """Use the Windows system voice in memory when optional pocket-tts is unavailable."""
    import wave
    import pythoncom
    import win32com.client

    stream = speaker = None
    pythoncom.CoInitialize()
    try:
        stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
        stream.Format.Type = 18  # SAFT16kHz16BitMono
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.AudioOutputStream = stream
        speaker.Speak(text[:2000])
        pcm = bytes(stream.GetData())
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        return output.getvalue()
    finally:
        speaker = None
        stream = None
        pythoncom.CoUninitialize()


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


def _reason(exc: Exception) -> str:
    """Short, safe fallback reason for clients (gRPC details can carry peer addresses / internal text)."""
    from app import nvidia_speech

    return "nvidia: " + (str(exc).split(":", 1)[0][:40] if isinstance(exc, nvidia_speech.SpeechError) else type(exc).__name__)


def backend() -> str:
    """nvidia | local, from SPATIAL_SPEECH_BACKEND (auto picks nvidia when it is usable)."""
    from app import nvidia_speech

    if settings.speech_backend == "local":
        return "local"
    if settings.speech_backend == "nvidia" or nvidia_speech.available():
        return "nvidia"
    return "local"


def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    if settings.speech_backend == "deepgram":  # explicit opt-in only; `auto` never picks it
        from app import deepgram_speech

        try:
            return deepgram_speech.transcribe(audio_bytes, language)
        except Exception as exc:  # network, auth, bad audio: the local model still answers
            fallback = _local_transcribe(audio_bytes, language)
            fallback["fallback_reason"] = "deepgram: " + (
                str(exc)[:40] if isinstance(exc, deepgram_speech.SpeechError) else type(exc).__name__
            )
            return fallback
    if backend() == "nvidia":
        from app import nvidia_speech

        try:
            return nvidia_speech.transcribe(audio_bytes, language)
        except Exception as exc:  # timeout, busy x3, auth, undecodable audio: the local model still answers
            fallback = _local_transcribe(audio_bytes, language)
            fallback["fallback_reason"] = _reason(exc)
            return fallback
    return _local_transcribe(audio_bytes, language)


def synthesize(text: str, voice: str | None = None) -> tuple[bytes | None, dict]:
    if not settings.tts_enabled:
        return None, {"status": "disabled"}
    if backend() == "nvidia":
        from app import nvidia_speech

        try:
            return nvidia_speech.synthesize(text, voice)
        except Exception as exc:
            wav, meta = _local_synthesize(text, None if (voice or "").startswith("Magpie") else voice)
            meta["fallback_reason"] = _reason(exc)
            return wav, meta
    return _local_synthesize(text, voice)


def warm() -> None:
    """Pay the first-use cost at server start, off the request path (the local models take 25-30 s to load)."""
    if not settings.audio_warm:
        return
    try:
        if backend() == "nvidia":
            from app import nvidia_speech

            nvidia_speech.warm()
            return
        from importlib.util import find_spec

        if find_spec("faster_whisper"):
            _whisper()
        if settings.tts_enabled and find_spec("pocket_tts"):
            _voice(settings.tts_voice)
        _touch()
    except Exception:
        pass  # the first request will report what is wrong


def audio_status() -> dict:
    from importlib.util import find_spec

    active = backend()
    pocket_tts_installed = find_spec("pocket_tts") is not None
    return {
        "backend": active,
        "stt": {
            "model": "parakeet-tdt-0.6b-v2 (NVIDIA hosted)" if active == "nvidia" else settings.stt_model,
            "device": "cloud" if active == "nvidia" else settings.stt_device,
            "installed": active == "nvidia" or find_spec("faster_whisper") is not None,
            "fallback": settings.stt_model if find_spec("faster_whisper") else None,
        },
        "tts": {
            "voice": settings.nvidia_tts_voice if active == "nvidia" else settings.tts_voice if pocket_tts_installed else "system",
            "enabled": settings.tts_enabled,
            "installed": active == "nvidia" or pocket_tts_installed or sys.platform == "win32",
            "fallback": settings.tts_voice if pocket_tts_installed else ("Windows system voice" if sys.platform == "win32" else None),
        },
    }
