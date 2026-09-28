"""Smoke-test the PyInstaller server binary without installing the desktop app.

Usage: pip install psutil && python scripts/smoke_bundle.py desktop/dist/spatial-server.exe
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil


def get(url: str, token: str | None = None) -> tuple[int, bytes]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=2) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else "desktop/dist/spatial-server.exe").resolve()
    if not binary.is_file():
        print(f"missing bundled server: {binary}", file=sys.stderr)
        return 2
    data_dir = Path(tempfile.mkdtemp(prefix="SpatialBundleSmoke-"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "LOCALAPPDATA": str(data_dir), "SPATIAL_PORT": str(port),
           "SPATIAL_AUDIO_WARM": "0", "SPATIAL_OCR": "0", "SPATIAL_PROVIDERS": "nothing"}
    process = subprocess.Popen([str(binary)], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    parent = psutil.Process(process.pid)
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError(f"server exited early with code {process.returncode}")
            try:
                status, _ = get(url + "/api/health")
                if status == 200:
                    break
            except (OSError, TimeoutError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("bundled server did not become healthy in 60 seconds")
        token = (data_dir / "Spatial" / "api.token").read_text(encoding="ascii").strip()
        assert len(token) == 64, "missing or malformed pairing token"
        assert get(url + "/api/contexts")[0] == 401, "anonymous context read was allowed"
        assert get(url + "/api/contexts", token)[0] == 200, "paired client was denied"
        assert b'"providers"' in get(url + "/api/health", token)[1], "authorized health was redacted"
        print(f"bundled server OK; auth enforced; child processes: {len(parent.children(recursive=True))}")
        print("isolated test data will be removed")
        return 0
    finally:
        # PyInstaller onefile has a parent and an extracted child. Stop only this launch's tree.
        try:
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        for item in [*children, parent]:
            try:
                item.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs([*children, parent], timeout=5)
        for remaining in alive:
            try:
                remaining.kill()
            except psutil.NoSuchProcess:
                pass
        process.wait(timeout=5)
        # Only remove the temporary directory created above, after checking its resolved parent.
        if data_dir.resolve().parent == Path(tempfile.gettempdir()).resolve():
            shutil.rmtree(data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
