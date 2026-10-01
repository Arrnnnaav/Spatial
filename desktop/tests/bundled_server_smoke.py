"""Launch the packaged server, then exercise its authenticated TTS → STT fallback path."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import io
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from faster_whisper.audio import decode_audio
from websockets.sync.client import connect


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = re.findall(r"[a-z0-9]+", reference.casefold())
    actual = re.findall(r"[a-z0-9]+", hypothesis.casefold())
    previous = list(range(len(expected) + 1))
    for row, word in enumerate(actual, 1):
        current = [row]
        for column, target in enumerate(expected, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (word != target),
                )
            )
        previous = current
    return previous[-1] / max(len(expected), 1)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    server = (
        root
        / "desktop"
        / "src-tauri"
        / "target"
        / "release"
        / "resources"
        / "spatial-server"
        / "spatial-server.exe"
    )
    smoke_root = root / "desktop" / ".build-temp"
    smoke_root.mkdir(exist_ok=True)
    if not server.is_file():
        raise SystemExit(f"Bundled server not found: {server}")

    with tempfile.TemporaryDirectory(prefix="live-e2e-", dir=smoke_root) as data:
        env = os.environ.copy()
        env.update(
            LOCALAPPDATA=data,
            SPATIAL_PORT="18787",
            SPATIAL_AUDIO_WARM="0",
            SPATIAL_SPEECH_BACKEND="local",
        )
        process = subprocess.Popen(
            [str(server)],
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            token_file = Path(data) / "Spatial" / "api.token"
            health = None
            for _ in range(40):
                if token_file.exists():
                    token = token_file.read_text(encoding="ascii").strip()
                    request = Request(
                        "http://127.0.0.1:18787/api/health",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    try:
                        with urlopen(request, timeout=2) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        pass
                time.sleep(0.5)
            if not health or not health.get("auth_required") or not health.get("audio"):
                if process.poll() is not None:
                    output, _ = process.communicate(timeout=5)
                    raise SystemExit(
                        f"Bundled server exited during startup ({process.returncode}): {output[-800:]}"
                    )
                raise SystemExit(
                    "Bundled server did not pass its authenticated health check"
                )
            speech_status = health["audio"]
            if not speech_status.get("stt", {}).get(
                "installed"
            ) or not speech_status.get("tts", {}).get("installed"):
                raise SystemExit(
                    "Bundled server reports a speech capability unavailable"
                )

            headers = {"Authorization": f"Bearer {token}"}
            tts_request = Request(
                "http://127.0.0.1:18787/api/tts",
                data=json.dumps(
                    {"text": "Spatial local speech recognition test."}
                ).encode(),
                headers={**headers, "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(tts_request, timeout=60) as response:
                speech = response.read()
                tts_backend = response.headers.get("X-TTS-Backend")
            if not speech.startswith(b"RIFF") or tts_backend not in {
                "windows-sapi",
                "local",
                "nvidia",
            }:
                raise SystemExit("Bundled TTS did not return a WAV")

            boundary = b"SpatialSmokeBoundary"
            stt_body = (
                b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="audio"; filename="smoke.wav"\r\n'
                b"Content-Type: audio/wav\r\n\r\n"
                + speech
                + b"\r\n--"
                + boundary
                + b"--\r\n"
            )
            stt_request = Request(
                "http://127.0.0.1:18787/api/stt",
                data=stt_body,
                headers={
                    **headers,
                    "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                },
                method="POST",
            )
            try:
                with urlopen(stt_request, timeout=120) as response:
                    transcript = json.load(response)
            except HTTPError as error:
                detail = json.load(error).get("detail", {})
                raise SystemExit(
                    f"Bundled STT failed: {detail.get('message', 'unavailable')}"
                ) from None
            if (
                transcript.get("status") != "ok"
                or not transcript.get("text", "").strip()
            ):
                raise SystemExit("Bundled STT did not return recognized text")
            wer = word_error_rate(
                "Spatial local speech recognition test", transcript["text"]
            )
            if wer > 0.2:
                raise SystemExit(
                    f"Bundled STT synthetic word error rate too high: {wer:.0%}"
                )

            clear_request = Request(
                "http://127.0.0.1:18787/api/contexts", headers=headers, method="DELETE"
            )
            with urlopen(clear_request, timeout=10) as response:
                if json.load(response).get("deleted") != 0:
                    raise SystemExit(
                        "Bundled history clear did not report an empty fresh profile"
                    )
            with urlopen(
                Request(
                    "http://127.0.0.1:18787/api/contexts?limit=200", headers=headers
                ),
                timeout=10,
            ) as response:
                if json.load(response) != []:
                    raise SystemExit("Bundled history is not empty after clear")

            pcm = (
                (
                    np.clip(
                        decode_audio(io.BytesIO(speech), sampling_rate=16000), -1, 1
                    )
                    * 32767
                )
                .astype("<i2")
                .tobytes()
            )
            desktop_token = (
                (Path(data) / "Spatial" / "desktop.token")
                .read_text(encoding="ascii")
                .strip()
            )
            desktop_headers = {**headers, "X-Spatial-Desktop": desktop_token, "Content-Type": "application/json"}
            created = json.load(urlopen(Request(
                "http://127.0.0.1:18787/api/dictations",
                data=json.dumps({"text": "Spatial smoke dictation entry.", "stt_provider": "local"}).encode(),
                headers=desktop_headers, method="POST"), timeout=30))
            if not created.get("id") or not created.get("title") or not created.get("summary"):
                raise SystemExit("Bundled dictation entry was not saved with a title and summary")
            listed = json.load(urlopen(Request("http://127.0.0.1:18787/api/dictations", headers=desktop_headers), timeout=10))
            if [e["id"] for e in listed] != [created["id"]]:
                raise SystemExit("Bundled dictation list does not contain the new entry")
            urlopen(Request(f"http://127.0.0.1:18787/api/dictations/{created['id']}", headers=desktop_headers, method="DELETE"), timeout=10).close()
            if json.load(urlopen(Request("http://127.0.0.1:18787/api/dictations", headers=desktop_headers), timeout=10)) != []:
                raise SystemExit("Bundled dictation entry was not deleted")
            retention_url = "http://127.0.0.1:18787/api/retention"
            put = json.load(urlopen(Request(retention_url, data=json.dumps({"days": 90}).encode(), headers=desktop_headers, method="PUT"), timeout=10))
            if put.get("days") != 90 or json.load(urlopen(Request(retention_url, headers=desktop_headers), timeout=10)).get("days") != 90:
                raise SystemExit("Bundled retention setting did not persist")
            urlopen(Request(retention_url, data=json.dumps({"days": None}).encode(), headers=desktop_headers, method="PUT"), timeout=10).close()
            soon = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
            task = json.load(urlopen(Request("http://127.0.0.1:18787/api/tasks", data=json.dumps({"text": "Smoke task"}).encode(),
                                             headers=desktop_headers, method="POST"), timeout=10))
            reminder = json.load(urlopen(Request("http://127.0.0.1:18787/api/reminders", data=json.dumps({"text": "Smoke reminder", "due_at": soon}).encode(),
                                                 headers=desktop_headers, method="POST"), timeout=10))
            due = json.load(urlopen(Request("http://127.0.0.1:18787/api/reminders/due", headers=desktop_headers), timeout=10))
            if [r["id"] for r in due] != [reminder["id"]]:
                raise SystemExit("Bundled due-reminder list is wrong")
            urlopen(Request(f"http://127.0.0.1:18787/api/reminders/{reminder['id']}/fired", data=b"", headers=desktop_headers, method="POST"), timeout=10).close()
            if json.load(urlopen(Request("http://127.0.0.1:18787/api/reminders/due", headers=desktop_headers), timeout=10)) != []:
                raise SystemExit("Bundled reminder fired twice")
            urlopen(Request(f"http://127.0.0.1:18787/api/reminders/{reminder['id']}", headers=desktop_headers, method="DELETE"), timeout=10).close()
            urlopen(Request(f"http://127.0.0.1:18787/api/tasks/{task['id']}", headers=desktop_headers, method="DELETE"), timeout=10).close()
            live_text = ""
            with connect(
                "ws://127.0.0.1:18787/api/stt/live",
                additional_headers={"Origin": "http://tauri.localhost"},
                open_timeout=10,
            ) as socket:
                socket.send(
                    json.dumps({"desktop_token": desktop_token, "api_token": token})
                )
                if json.loads(socket.recv(timeout=10)).get("type") != "ready":
                    raise SystemExit("Bundled live STT did not become ready")
                for offset in range(0, len(pcm), 8192):
                    socket.send(pcm[offset : offset + 8192])
                    if offset + 8192 < len(pcm):
                        time.sleep(0.2)
                socket.send(json.dumps({"type": "end"}))
                while True:
                    update = json.loads(socket.recv(timeout=120))
                    if update.get("type") == "transcript":
                        live_text = update.get("text", "")
                    elif update.get("type") == "error":
                        raise SystemExit("Bundled live STT failed")
                    elif update.get("type") == "done":
                        break
            live_wer = word_error_rate(
                "Spatial local speech recognition test", live_text
            )
            if not live_text or live_wer > 0.4:
                raise SystemExit(
                    f"Bundled live STT preview failed: synthetic WER {live_wer:.0%}"
                )

            print(
                "bundled server ready; authenticated health OK; "
                f"protocol={health['protocol_version']}; speech={health['audio']['backend']}; "
                f"history clear OK; dictation entries OK; tasks+reminders OK; retention OK; TTS={tts_backend}; live WER={live_wer:.0%}; final WER={wer:.0%}"
            )
        finally:
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
