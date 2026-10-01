"""Provider API keys for the installed app: written only to the per-user server.env, never returned or logged.
The server reads providers once at start, so a change needs a restart (`restart_required`)."""

from __future__ import annotations

import os
import re

from app import config

ALLOWED = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "NVIDIA_API_KEY",
    "TYPESAFE_API_KEY",
    "TAVILY_API_KEY",
    "DEEPGRAM_API_KEY",
)
VALID_VALUE = re.compile(
    r"[A-Za-z0-9_.~+/=:-]{8,400}"
)  # key charset: no spaces, quotes or newlines


def status() -> dict[str, bool]:
    return {name: bool((os.environ.get(name) or "").strip()) for name in ALLOWED}


def set_key(name: str, value: str) -> bool:
    """Set (or, with an empty value, remove) one key in the per-user file. Raises ValueError for unknown names or
    malformed values. Returns whether the key is configured afterwards."""
    if name not in ALLOWED:
        raise ValueError("unknown key name")
    value = value.strip()
    if value and not VALID_VALUE.fullmatch(value):
        raise ValueError("malformed key value")
    path = config.user_env_path()
    if path is None:
        raise ValueError("no per-user directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    lines = [
        line for line in lines if not re.match(rf"^\s*{re.escape(name)}\s*=", line)
    ]
    if value:
        lines.append(f"{name}={value}")
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    temp = path.with_suffix(".tmp")
    temp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    temp.replace(path)
    return bool(value)
