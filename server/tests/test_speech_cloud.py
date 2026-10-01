import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import audio, deepgram_speech, main, prefs
from app.config import settings


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    prefs.set("speech_cloud", "")
    monkeypatch.setattr(settings, "speech_backend", "auto")
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-secret-key", raising=False)
    monkeypatch.setattr(
        deepgram_speech,
        "_client",
        lambda: SimpleNamespace(
            post=lambda *a, **k: SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "metadata": {"duration": 1.0},
                    "results": {
                        "channels": [{"alternatives": [{"transcript": "cloud"}]}]
                    },
                },
            )
        ),
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
    yield
    prefs.set("speech_cloud", "")


def test_cloud_is_used_only_when_the_toggle_is_on_and_a_key_exists(monkeypatch):
    assert audio.transcribe(b"x")["backend"] == "local"  # default: private, on-device
    prefs.set("speech_cloud", "1")
    assert audio.transcribe(b"x")["backend"] == "deepgram"
    monkeypatch.setattr(settings, "deepgram_api_key", None, raising=False)
    assert (
        audio.transcribe(b"x")["backend"] == "local"
    )  # toggle on but no key: never errors, stays local


def test_forcing_local_by_environment_beats_the_toggle(monkeypatch):
    prefs.set("speech_cloud", "1")
    monkeypatch.setattr(settings, "speech_backend", "local")
    assert audio.transcribe(b"x")["backend"] == "local"


def test_audio_status_reports_the_active_speech_backend():
    assert audio.audio_status()["backend"] != "deepgram"
    prefs.set("speech_cloud", "1")
    status = audio.audio_status()
    assert (
        status["backend"] == "deepgram"
        and status["stt"]["device"] == "cloud"
        and status["stt"]["installed"] is True
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "secret", raising=False)
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "dt", raising=False
    )
    with TestClient(main.app) as c:
        c.headers.update({"Authorization": "Bearer secret", "X-Spatial-Desktop": "dt"})
        yield c


def test_route_toggles_and_never_returns_the_key(client, monkeypatch):
    first = client.get("/api/speech/cloud")
    assert first.json() == {
        "enabled": False,
        "key_configured": True,
        "provider": "Deepgram",
    }
    assert (
        client.put("/api/speech/cloud", json={"enabled": True}).json()["enabled"]
        is True
    )
    assert "dg-secret-key" not in client.get("/api/speech/cloud").text
    assert (
        client.put("/api/speech/cloud", json={"enabled": False}).json()["enabled"]
        is False
    )
    monkeypatch.setattr(settings, "deepgram_api_key", None, raising=False)
    refused = client.put("/api/speech/cloud", json={"enabled": True})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NO_KEY"
    assert client.get("/api/speech/cloud").json()["key_configured"] is False


def test_route_needs_both_tokens(client):
    web = TestClient(main.app)
    web.headers.update({"Authorization": "Bearer secret"})
    assert web.get("/api/speech/cloud").status_code == 403
    assert web.put("/api/speech/cloud", json={"enabled": True}).status_code == 403
