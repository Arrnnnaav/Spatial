"""Launch the packaged server with isolated app data and verify its authenticated health route."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    server = root / "desktop" / "src-tauri" / "target" / "release" / "resources" / "spatial-server.exe"
    smoke_root = root / "desktop" / "install-smoke"
    smoke_root.mkdir(exist_ok=True)
    if not server.is_file():
        raise SystemExit(f"Bundled server not found: {server}")

    with tempfile.TemporaryDirectory(prefix="live-e2e-", dir=smoke_root) as data:
        env = os.environ.copy()
        env.update(LOCALAPPDATA=data, SPATIAL_PORT="18787", SPATIAL_AUDIO_WARM="0")
        process = subprocess.Popen(
            [str(server)], env=env, creationflags=subprocess.CREATE_NO_WINDOW
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
                raise SystemExit("Bundled server did not pass its authenticated health check")
            print(
                "bundled server ready; authenticated health OK; "
                f"protocol={health['protocol_version']}; speech={health['audio']['backend']}"
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
