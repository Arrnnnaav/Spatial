import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest

from app import audio, config, deepgram_speech
from app.config import settings

CANNED = {
    "metadata": {"duration": 3.2},
    "results": {
        "channels": [{"alternatives": [{"transcript": "call Sam about the budget."}]}]
    },
}


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else CANNED

    def json(self):
        return self._payload


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-secret-key", raising=False)


def test_available_needs_a_key(monkeypatch):
    monkeypatch.setattr(settings, "deepgram_api_key", None, raising=False)
    assert deepgram_speech.available() is False
    monkeypatch.setattr(settings, "deepgram_api_key", "k", raising=False)
    assert deepgram_speech.available() is True


def test_transcribe_parses_response_and_sends_token_header_and_language(
    key, monkeypatch
):
    seen = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers, size=len(content), timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(deepgram_speech.httpx, "post", fake_post)
    result = deepgram_speech.transcribe(b"\x00" * 10, "en-GB")
    assert result == {
        "status": "ok",
        "text": "call Sam about the budget.",
        "language": "en-GB",
        "duration": 3.2,
        "model": settings.deepgram_model,
        "backend": "deepgram",
    }
    assert seen["headers"]["Authorization"] == "Token dg-secret-key"
    assert (
        "language=en-GB" in seen["url"]
        and f"model={settings.deepgram_model}" in seen["url"]
    )
    assert "smart_format=true" in seen["url"] and seen["size"] == 10


def test_auth_failure_raises_a_safe_error_without_the_key(key, monkeypatch):
    monkeypatch.setattr(
        deepgram_speech.httpx,
        "post",
        lambda *a, **k: FakeResponse(401, {"err_msg": "dg-secret-key rejected"}),
    )
    with pytest.raises(deepgram_speech.SpeechError) as error:
        deepgram_speech.transcribe(b"x")
    assert "dg-secret-key" not in str(error.value) and "401" in str(error.value)


def test_audio_uses_deepgram_when_selected_and_falls_back_to_local(key, monkeypatch):
    monkeypatch.setattr(settings, "speech_backend", "deepgram")
    monkeypatch.setattr(deepgram_speech.httpx, "post", lambda *a, **k: FakeResponse())
    assert audio.transcribe(b"x")["backend"] == "deepgram"

    monkeypatch.setattr(
        deepgram_speech.httpx, "post", lambda *a, **k: FakeResponse(500, {})
    )
    monkeypatch.setattr(
        audio,
        "_local_transcribe",
        lambda data, language=None: {
            "status": "ok",
            "text": "local",
            "backend": "local",
        },
    )
    fallback = audio.transcribe(b"x")
    assert fallback["backend"] == "local" and fallback["fallback_reason"].startswith(
        "deepgram:"
    )


def test_deepgram_is_never_picked_by_auto(key, monkeypatch):
    monkeypatch.setattr(settings, "speech_backend", "auto")
    assert audio.backend() != "deepgram"


def test_user_env_file_is_loaded_without_overriding_real_environment(
    tmp_path, monkeypatch
):
    env_file = tmp_path / "server.env"
    env_file.write_text(
        "DEEPGRAM_API_KEY=from-file\nSPATIAL_TEST_KEEP=file\n", encoding="utf-8"
    )
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("SPATIAL_TEST_KEEP", "real")
    config.load_user_env(env_file)
    assert os.environ["DEEPGRAM_API_KEY"] == "from-file"
    assert os.environ["SPATIAL_TEST_KEEP"] == "real"
    config.load_user_env(tmp_path / "missing.env")  # absent file is fine
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
