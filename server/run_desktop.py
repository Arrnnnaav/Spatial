"""Entry point for the bundled local server. User data stays outside the executable bundle."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def pairing_token(base: Path) -> str:
    """Persist a random bearer token for the bundled server and browser extension."""
    path = base / "api.token"
    try:
        token = path.read_text(encoding="ascii").strip()
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
            return token
    except FileNotFoundError:
        pass
    token = secrets.token_hex(32)
    # The app data directory is private to the Windows user; do not put this in logs or process args.
    path.write_text(token, encoding="ascii")
    return token


def main() -> None:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".spatial") / "Spatial"
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SPATIAL_DB", str(base / "spatial.db"))
    os.environ.setdefault("SPATIAL_ENV_FILE", str(base / "server.env"))
    os.environ["SPATIAL_HOST"] = "127.0.0.1"
    os.environ["SPATIAL_API_TOKEN"] = pairing_token(base)

    import uvicorn
    from app.config import settings
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
