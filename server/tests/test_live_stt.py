import queue
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import main
from app import nvidia_speech


def test_live_stt_authenticates_desktop_and_streams_transcript(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    monkeypatch.setitem(
        main.settings.providers, "nvidia", SimpleNamespace(api_key="configured")
    )
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "desktop-token"
    )

    def fake_stream(audio, publish):
        assert audio.get(timeout=2) == b"\x01\x00"
        assert audio.get(timeout=2) is None
        publish({"type": "transcript", "text": "hello there", "final": True})

    monkeypatch.setattr(main, "nvidia_stream_transcribe", fake_stream)
    with TestClient(main.app) as client:
        with client.websocket_connect(
            "/api/stt/live", headers={"Origin": "http://tauri.localhost"}
        ) as socket:
            socket.send_json(
                {"desktop_token": "desktop-token", "api_token": "test-token"}
            )
            assert socket.receive_json() == {"type": "ready"}
            socket.send_bytes(b"\x01\x00")
            socket.send_json({"type": "end"})
            assert socket.receive_json() == {
                "type": "transcript",
                "text": "hello there",
                "final": True,
            }


def test_live_stt_keeps_running_without_nvidia_key(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    monkeypatch.setitem(
        main.settings.providers, "nvidia", SimpleNamespace(api_key=None)
    )
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "desktop-token"
    )

    def fake_local_stream(audio, publish):
        assert audio.get(timeout=2) == b"\x01\x00"
        assert audio.get(timeout=2) is None
        publish({"type": "transcript", "text": "local preview", "final": False})

    monkeypatch.setattr(main, "nvidia_stream_transcribe", fake_local_stream)
    with TestClient(main.app) as client:
        with client.websocket_connect(
            "/api/stt/live", headers={"Origin": "http://tauri.localhost"}
        ) as socket:
            socket.send_json(
                {"desktop_token": "desktop-token", "api_token": "test-token"}
            )
            assert socket.receive_json() == {"type": "ready"}
            socket.send_bytes(b"\x01\x00")
            socket.send_json({"type": "end"})
            assert socket.receive_json() == {
                "type": "transcript",
                "text": "local preview",
                "final": False,
            }


def test_live_stt_flushes_last_transcript_and_sends_done(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "desktop-token"
    )

    def fake_stream(audio, publish):
        assert audio.get(timeout=2) is None
        publish({"type": "transcript", "text": "last words", "final": True})

    monkeypatch.setattr(main, "nvidia_stream_transcribe", fake_stream)
    with TestClient(main.app) as client:
        with client.websocket_connect(
            "/api/stt/live", headers={"Origin": "http://tauri.localhost"}
        ) as socket:
            socket.send_json(
                {"desktop_token": "desktop-token", "api_token": "test-token"}
            )
            assert socket.receive_json() == {"type": "ready"}
            socket.send_json({"type": "end"})
            assert socket.receive_json() == {
                "type": "transcript",
                "text": "last words",
                "final": True,
            }
            assert socket.receive_json() == {"type": "done"}


def test_live_stt_rejects_web_origin(monkeypatch):
    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/stt/live", headers={"Origin": "https://example.com"}
            ):
                pass


def test_idle_live_stt_socket_stops_worker(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    monkeypatch.setitem(
        main.settings.providers, "nvidia", SimpleNamespace(api_key="configured")
    )
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "desktop-token"
    )
    monkeypatch.setattr(main, "LIVE_STT_IDLE_SECONDS", 0.01)

    def wait_for_stop(audio, _publish):
        assert audio.get(timeout=2) is None

    monkeypatch.setattr(main, "nvidia_stream_transcribe", wait_for_stop)
    with TestClient(main.app) as client:
        with client.websocket_connect(
            "/api/stt/live", headers={"Origin": "http://tauri.localhost"}
        ) as socket:
            socket.send_json(
                {"desktop_token": "desktop-token", "api_token": "test-token"}
            )
            assert socket.receive_json() == {"type": "ready"}
            assert socket.receive_json()["type"] == "error"


def test_live_stt_has_absolute_session_limit(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    monkeypatch.setitem(
        main.settings.providers, "nvidia", SimpleNamespace(api_key="configured")
    )
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "desktop-token"
    )
    monkeypatch.setattr(main, "LIVE_STT_IDLE_SECONDS", 5)
    monkeypatch.setattr(main, "LIVE_STT_MAX_SECONDS", 0.01)

    def wait_for_stop(audio, _publish):
        assert audio.get(timeout=2) == b"\x01\x00"
        assert audio.get(timeout=2) is None

    monkeypatch.setattr(main, "nvidia_stream_transcribe", wait_for_stop)
    with TestClient(main.app) as client:
        with client.websocket_connect(
            "/api/stt/live", headers={"Origin": "http://tauri.localhost"}
        ) as socket:
            socket.send_json(
                {"desktop_token": "desktop-token", "api_token": "test-token"}
            )
            assert socket.receive_json() == {"type": "ready"}
            socket.send_bytes(b"\x01\x00")
            assert socket.receive_json()["type"] == "error"


def test_nvidia_live_uses_bounded_offline_windows_when_online_model_is_disabled(
    monkeypatch,
):
    class OfflineOnlyService:
        def streaming_response_generator(self, audio_chunks, _config):
            next(iter(audio_chunks))
            raise RuntimeError("online model unavailable")

    monkeypatch.setattr(nvidia_speech, "_service", lambda *_: OfflineOnlyService())
    monkeypatch.setattr(main.settings, "speech_backend", "nvidia")
    phrases = iter(("first call", "call second"))
    monkeypatch.setattr("app.audio.transcribe", lambda *_: {"text": next(phrases)})
    chunks = queue.Queue()
    for _ in range(5):
        chunks.put(b"\x01\x00" * 16000)  # one second each
    chunks.put(None)
    updates = []

    nvidia_speech.stream_transcribe(chunks, updates.append)

    assert [item["text"] for item in updates] == ["first call", "first call second"]


def test_local_live_uses_bounded_windows_without_configured_provider(monkeypatch):
    monkeypatch.setattr(main.settings, "speech_backend", "local")
    monkeypatch.setattr(nvidia_speech, "available", lambda: True)
    phrases = iter(("first call", "call second"))
    monkeypatch.setattr("app.audio.transcribe", lambda *_: {"text": next(phrases)})
    chunks = queue.Queue()
    for _ in range(5):
        chunks.put(b"\x01\x00" * 16000)
    chunks.put(None)
    updates = []

    nvidia_speech.stream_transcribe(chunks, updates.append)

    assert [item["text"] for item in updates] == ["first call", "first call second"]
