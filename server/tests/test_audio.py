"""Speech in/out: NVIDIA hosted first, local fallback, retries, chunking, endpoints. No network, no model loads."""

import io
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import audio, main, nvidia_speech  # noqa: E402
from app.config import settings  # noqa: E402


def wav_bytes(seconds=0.5, rate=16000):
    return nvidia_speech.pcm16_wav(b"\x00\x00" * int(seconds * rate), rate)


class GrpcError(Exception):
    def __init__(self, name):
        super().__init__(name)
        self._name = name

    def code(self):
        return SimpleNamespace(name=self._name)


@pytest.fixture
def local_calls(monkeypatch):
    calls = []

    def fake_stt(data, language=None):
        calls.append("stt")
        return {
            "status": "ok",
            "text": "local words",
            "language": "en",
            "duration": 0.5,
            "model": "base",
            "backend": "local",
        }

    def fake_tts(text, voice=None):
        calls.append(("tts", voice))
        return wav_bytes(), {
            "status": "ok",
            "sample_rate": 16000,
            "voice": voice or "alba",
            "seconds": 0.5,
            "backend": "local",
        }

    monkeypatch.setattr(audio, "_local_transcribe", fake_stt)
    monkeypatch.setattr(audio, "_local_synthesize", fake_tts)
    return calls


@pytest.fixture
def nvidia_on(monkeypatch):
    monkeypatch.setattr(settings, "speech_backend", "auto")
    monkeypatch.setattr(nvidia_speech, "available", lambda: True)


# --- backend choice + fallback ---------------------------------------------------------------------------------


def test_backend_choice(monkeypatch):
    monkeypatch.setattr(nvidia_speech, "available", lambda: True)
    for configured, expected in (
        ("local", "local"),
        ("nvidia", "nvidia"),
        ("auto", "nvidia"),
    ):
        monkeypatch.setattr(settings, "speech_backend", configured)
        assert audio.backend() == expected
    monkeypatch.setattr(nvidia_speech, "available", lambda: False)
    assert audio.backend() == "local"


def test_nvidia_used_first(nvidia_on, local_calls, monkeypatch):
    monkeypatch.setattr(
        nvidia_speech,
        "transcribe",
        lambda data, language=None: {
            "status": "ok",
            "text": "hosted",
            "backend": "nvidia",
        },
    )
    assert audio.transcribe(wav_bytes())["text"] == "hosted" and local_calls == []


def test_stt_falls_back_to_local_on_nvidia_error(nvidia_on, local_calls, monkeypatch):
    def boom(data, language=None):
        raise nvidia_speech.SpeechError("timeout")

    monkeypatch.setattr(nvidia_speech, "transcribe", boom)
    result = audio.transcribe(wav_bytes())
    assert result["text"] == "local words" and result["backend"] == "local"
    assert "timeout" in result["fallback_reason"] and local_calls == ["stt"]


def test_tts_fallback_drops_magpie_voice(nvidia_on, local_calls, monkeypatch):
    def boom(text, voice=None):
        raise nvidia_speech.SpeechError("UNAUTHENTICATED")

    monkeypatch.setattr(nvidia_speech, "synthesize", boom)
    wav, meta = audio.synthesize("hello", "Magpie-Multilingual.EN-US.Aria")
    assert wav and meta["backend"] == "local" and local_calls == [("tts", None)]


def test_tts_disabled(monkeypatch):
    monkeypatch.setattr(settings, "tts_enabled", False)
    assert audio.synthesize("hi") == (None, {"status": "disabled"})


def test_windows_tts_uses_system_voice_if_local_model_missing(monkeypatch):
    monkeypatch.setattr(settings, "tts_enabled", True)
    monkeypatch.setattr(settings, "audio_idle_unload_seconds", 0)
    monkeypatch.setattr(audio.sys, "platform", "win32")

    def missing_model():
        raise ModuleNotFoundError("pocket_tts")

    monkeypatch.setattr(audio, "_tts", missing_model)
    monkeypatch.setattr(audio, "_windows_synthesize", lambda text: wav_bytes())
    wav, meta = audio._local_synthesize("hello")
    assert wav.startswith(b"RIFF")
    assert meta["backend"] == "windows-sapi" and meta["voice"] == "system"


def test_windows_tts_status_reports_system_fallback(monkeypatch):
    import importlib.util

    monkeypatch.setattr(audio.sys, "platform", "win32")
    monkeypatch.setattr(settings, "speech_backend", "local")
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "pocket_tts" else find_spec(name))
    status = audio.audio_status()
    assert status["tts"]["installed"] and status["tts"]["fallback"] == "Windows system voice"


# --- hosted client: retries, time budget, chunking, model routing -----------------------------------------------


def test_busy_errors_are_retried_then_succeed(monkeypatch):
    monkeypatch.setattr(nvidia_speech.time, "sleep", lambda s: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise GrpcError("UNAVAILABLE")
        return "ok"

    assert nvidia_speech._call(flaky) == "ok" and len(attempts) == 3


def test_busy_three_times_gives_up(monkeypatch):
    monkeypatch.setattr(nvidia_speech.time, "sleep", lambda s: None)
    attempts = []

    def busy():
        attempts.append(1)
        raise GrpcError("RESOURCE_EXHAUSTED")

    with pytest.raises(nvidia_speech.SpeechError):
        nvidia_speech._call(busy)
    assert len(attempts) == settings.provider_attempts == 3


def test_auth_error_is_not_retried():
    attempts = []

    def denied():
        attempts.append(1)
        raise GrpcError("UNAUTHENTICATED")

    with pytest.raises(nvidia_speech.SpeechError, match="UNAUTHENTICATED"):
        nvidia_speech._call(denied)
    assert len(attempts) == 1


def test_hard_time_budget(monkeypatch):
    import time

    monkeypatch.setattr(settings, "speech_timeout", 0.2)
    started = time.monotonic()
    with pytest.raises(nvidia_speech.SpeechError, match="timeout"):
        nvidia_speech._call(lambda: time.sleep(2))
    assert time.monotonic() - started < 1.0


def test_chunks_stay_under_limit_and_keep_text():
    text = ("This is a sentence about gradients. " * 120).strip()
    parts = nvidia_speech._chunks(text)
    assert len(parts) > 1 and all(len(p) <= nvidia_speech.TTS_MAX_CHARS for p in parts)
    assert " ".join(parts) == text
    assert nvidia_speech._chunks("x" * 3200) == ["x" * 1500, "x" * 1500, "x" * 200]


class FakeASR:
    def __init__(self, text="The learning rate controls the step size."):
        self.text, self.seen = text, []

    def offline_recognize(self, wav, config):
        self.seen.append((wav[:4], config.language_code))
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    alternatives=[SimpleNamespace(transcript=self.text + " ")]
                )
            ]
        )


def test_hosted_transcribe_routes_english_and_other_languages(monkeypatch):
    services = {}

    def fake_service(kind, function_id):
        return services.setdefault(function_id, FakeASR())

    monkeypatch.setattr(nvidia_speech, "_service", fake_service)
    en = nvidia_speech.transcribe(wav_bytes(1.0))
    fr = nvidia_speech.transcribe(wav_bytes(), "fr")
    assert (
        en["text"] == "The learning rate controls the step size."
        and en["model"] == "parakeet-tdt-0.6b-v2"
    )
    assert en["duration"] == 1.0 and en["backend"] == "nvidia"
    assert fr["model"] == "whisper-large-v3"
    assert services[settings.nvidia_asr_function].seen == [(b"RIFF", "en-US")]
    assert services[settings.nvidia_asr_multilingual_function].seen == [(b"RIFF", "fr")]


def test_hosted_synthesize_joins_chunks_into_one_wav(monkeypatch):
    calls = []

    class FakeTTS:
        def synthesize(
            self, text, voice_name=None, language_code=None, sample_rate_hz=None
        ):
            calls.append((len(text), voice_name, sample_rate_hz))
            return SimpleNamespace(audio=b"\x01\x00" * 2205)  # 0.1 s at 22.05 kHz

    monkeypatch.setattr(nvidia_speech, "_service", lambda kind, fid: FakeTTS())
    wav, meta = nvidia_speech.synthesize(
        "Short one. " * 300, voice="alba"
    )  # local voice name -> default Magpie voice
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == 22050 and w.getnframes() == 2205 * len(calls)
    assert len(calls) >= 2 and all(
        voice == settings.nvidia_tts_voice for _, voice, _ in calls
    )
    assert meta["backend"] == "nvidia" and meta["seconds"] == round(0.1 * len(calls), 2)


# --- endpoints + status + warm -----------------------------------------------------------------------------------


def test_stt_endpoint(local_calls):
    with TestClient(main.app) as client:
        ok = client.post(
            "/api/stt", files={"audio": ("q.webm", wav_bytes(), "audio/webm")}
        )
        empty = client.post("/api/stt", files={"audio": ("q.webm", b"", "audio/webm")})
    assert ok.status_code == 200 and ok.json()["text"] == "local words"
    assert empty.status_code == 400 and empty.json()["detail"]["code"] == "EMPTY_AUDIO"


def test_stt_unavailable_is_503(monkeypatch):
    monkeypatch.setattr(
        audio,
        "_local_transcribe",
        lambda d, language=None: {
            "status": "unavailable",
            "error": "no model",
            "text": "",
        },
    )
    with TestClient(main.app) as client:
        r = client.post(
            "/api/stt", files={"audio": ("q.webm", wav_bytes(), "audio/webm")}
        )
    assert r.status_code == 503 and r.json()["detail"]["code"] == "STT_UNAVAILABLE"


def test_tts_endpoint_returns_wav_and_backend(local_calls):
    with TestClient(main.app) as client:
        r = client.post("/api/tts", json={"text": "hello there"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.headers["x-tts-backend"] == "local"


def test_status_reports_backend(nvidia_on):
    status = audio.audio_status()
    assert (
        status["backend"] == "nvidia"
        and status["stt"]["device"] == "cloud"
        and status["stt"]["installed"]
    )


def test_warm_opens_hosted_channels_and_respects_switch(nvidia_on, monkeypatch):
    warmed = []
    monkeypatch.setattr(nvidia_speech, "warm", lambda: warmed.append(1))
    monkeypatch.setattr(settings, "audio_warm", False)
    audio.warm()
    assert warmed == []
    monkeypatch.setattr(settings, "audio_warm", True)
    audio.warm()
    assert warmed == [1]


def test_fallback_reason_hides_exception_details(nvidia_on, local_calls, monkeypatch):
    def boom(data, language=None):
        raise nvidia_speech.SpeechError("UNAVAILABLE: peer 10.0.0.1:443 internal debug text")

    monkeypatch.setattr(nvidia_speech, "transcribe", boom)
    assert audio.transcribe(wav_bytes())["fallback_reason"] == "nvidia: UNAVAILABLE"


def test_bad_language_is_400():
    with TestClient(main.app) as client:
        r = client.post("/api/stt", data={"language": "en;DROP"}, files={"audio": ("q.webm", wav_bytes(), "audio/webm")})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_LANGUAGE"


def test_local_stt_error_is_unavailable_not_500(monkeypatch):
    class Model:
        def transcribe(self, *a, **k):
            raise ValueError("'xx' is not a valid language code")

    monkeypatch.setattr(audio, "_whisper", lambda: Model())
    assert audio._local_transcribe(wav_bytes(), "xx") == {"status": "unavailable", "error": "ValueError", "text": ""}


def test_tts_has_one_overall_budget(monkeypatch):
    import time

    class SlowTTS:
        def synthesize(self, text, **kwargs):
            time.sleep(0.15)
            return SimpleNamespace(audio=b"\x00\x00")

    monkeypatch.setattr(settings, "speech_timeout", 0.1)  # per call 0.1 s would time out; whole request 0.2 s
    monkeypatch.setattr(nvidia_speech, "_service", lambda kind, fid: SlowTTS())
    with pytest.raises(nvidia_speech.SpeechError, match="timeout"):
        nvidia_speech.synthesize("One. " * 900)


def test_local_stt_accepts_region_language_codes(monkeypatch):
    """/api/stt allows codes like en-US / en-GB; faster-whisper only knows the primary subtag."""
    seen = []

    class FakeModel:
        def transcribe(self, _audio, language=None, **_kwargs):
            seen.append(language)
            if language and "-" in language:
                raise ValueError("unsupported language")
            return iter([SimpleNamespace(text=" hello ")]), SimpleNamespace(language="en", duration=1.0)

    monkeypatch.setattr(audio, "_whisper", lambda: FakeModel())
    for code in ("en-GB", "en-US", "EN", None, "pt-BR"):
        assert audio._local_transcribe(b"x", code)["status"] == "ok", code
    assert seen == ["en", "en", "en", None, "pt"]
