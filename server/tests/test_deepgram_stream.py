import json
import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from websockets.sync.server import serve

from app import audio, deepgram_speech, nvidia_speech, prefs
from app.config import settings


def result(text, final, speech_final=False):
    return json.dumps(
        {
            "type": "Results",
            "is_final": final,
            "speech_final": speech_final,
            "channel": {"alternatives": [{"transcript": text}]},
        }
    )


@pytest.fixture
def fake_deepgram(monkeypatch):
    """A local stand-in for wss://api.deepgram.com/v1/listen that scripts its replies."""
    seen = {"auth": None, "path": None, "frames": 0, "closed_stream": False}
    script = {"replies": []}  # list of (after_n_frames, message)

    def handler(ws):
        seen["auth"] = ws.request.headers.get("Authorization")
        seen["path"] = ws.request.path
        replies = list(script["replies"])
        try:
            for message in ws:
                if isinstance(message, bytes):
                    seen["frames"] += 1
                    while replies and replies[0][0] <= seen["frames"]:
                        ws.send(replies.pop(0)[1])
                elif json.loads(message).get("type") == "CloseStream":
                    seen["closed_stream"] = True
                    for (
                        _,
                        reply,
                    ) in (
                        replies
                    ):  # flush what is left, like the real service does on close
                        ws.send(reply)
                    break
        except Exception:
            pass

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.socket.getsockname()[1]
    monkeypatch.setattr(deepgram_speech, "WS_URL", f"ws://127.0.0.1:{port}/v1/listen")
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-secret-key", raising=False)
    yield seen, script
    server.shutdown()


def run_stream(frames=3):
    chunks, updates = queue.Queue(), []
    for _ in range(frames):
        chunks.put(b"\x01\x00" * 8000)
    chunks.put(None)
    consumed = deepgram_speech.stream_transcribe(chunks, updates.append)
    return updates, consumed


def test_stream_sends_pcm_with_token_and_stitches_interim_and_final(fake_deepgram):
    seen, script = fake_deepgram
    script["replies"] = [
        (1, result("call sam", False)),
        (2, result("Call Sam.", True)),
        (3, result("about the", False)),
        (99, result("about the budget.", True)),
    ]
    updates, consumed = run_stream()
    assert seen["auth"] == "Token dg-secret-key"
    assert (
        "encoding=linear16" in seen["path"]
        and "sample_rate=16000" in seen["path"]
        and "interim_results=true" in seen["path"]
    )
    assert seen["frames"] == 3 and seen["closed_stream"] is True
    texts = [u["text"] for u in updates]
    assert texts == [
        "call sam",
        "Call Sam.",
        "Call Sam. about the",
        "Call Sam. about the budget.",
    ]
    assert updates[-1]["final"] is True and updates[0]["final"] is False
    assert (
        len(consumed) == 3
    )  # kept so a mid-stream failure can fall back to local windows


def test_empty_transcripts_are_not_published(fake_deepgram):
    seen, script = fake_deepgram
    script["replies"] = [(1, result("", False)), (2, result("hello", True))]
    updates, _ = run_stream(2)
    assert [u["text"] for u in updates] == ["hello"]


def test_connection_failure_raises_a_key_free_error(monkeypatch):
    monkeypatch.setattr(deepgram_speech, "WS_URL", "ws://127.0.0.1:1/v1/listen")
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-secret-key", raising=False)
    with pytest.raises(deepgram_speech.SpeechError) as error:
        run_stream(1)
    assert "dg-secret-key" not in str(error.value)


def test_nvidia_entry_point_streams_through_deepgram_when_cloud_is_on(
    fake_deepgram, monkeypatch
):
    seen, script = fake_deepgram
    script["replies"] = [(1, result("hello there", True))]
    prefs.set("speech_cloud", "1")
    monkeypatch.setattr(settings, "speech_backend", "auto")
    try:
        chunks, updates = queue.Queue(), []
        chunks.put(b"\x01\x00" * 8000)
        chunks.put(None)
        nvidia_speech.stream_transcribe(chunks, updates.append)
    finally:
        prefs.set("speech_cloud", "")
    assert (
        updates
        and updates[-1]["text"] == "hello there"
        and seen["auth"] == "Token dg-secret-key"
    )


def test_failed_cloud_stream_falls_back_to_local_windows(monkeypatch):
    monkeypatch.setattr(deepgram_speech, "WS_URL", "ws://127.0.0.1:1/v1/listen")
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-secret-key", raising=False)
    monkeypatch.setattr(settings, "speech_backend", "auto")
    monkeypatch.setattr(audio, "transcribe", lambda *_: {"text": "local words"})
    prefs.set("speech_cloud", "1")
    try:
        chunks, updates = queue.Queue(), []
        for _ in range(5):
            chunks.put(b"\x01\x00" * 16000)
        chunks.put(None)
        nvidia_speech.stream_transcribe(chunks, updates.append)
    finally:
        prefs.set("speech_cloud", "")
    assert updates and updates[-1]["text"] == "local words"
