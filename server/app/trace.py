"""Opt-in local trace log: one JSON line per ask with the resolution trace (marks, candidates, what was
resolved, question, answer, timings). Separate from the SQLite history, and never contains image bytes:
records are built from an allowlist, and data: URLs are stripped. A broken log directory disables tracing
for the process instead of failing asks."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings
from app.contracts import SemanticResolution, SpatialContext

TRACE_VERSION = 1
logger = logging.getLogger("spatial.trace")
_lock = threading.Lock()
_state: dict[str, str | None] = {"error": None}


def default_log_dir() -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
            / "Spatial"
            / "logs"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Spatial"
    return (
        Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
        / "spatial"
        / "logs"
    )


def log_dir() -> Path:
    return Path(settings.trace_dir) if settings.trace_dir else default_log_dir()


def _config_path() -> Path:
    return log_dir() / "config.json"


def enabled() -> bool:
    if _state["error"]:
        return False
    try:
        value = json.loads(_config_path().read_text(encoding="utf-8")).get("enabled")
        if isinstance(value, bool):
            return value
    except (OSError, ValueError, AttributeError):
        pass
    return settings.trace_enabled


def set_enabled(value: bool) -> None:
    """Runtime switch (popup toggle), persisted next to the logs. Raises OSError if the directory is unusable."""
    with _lock:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        _config_path().write_text(json.dumps({"enabled": value}), encoding="utf-8")
        _state["error"] = None


def _no_data_url(value: str | None) -> str | None:
    return None if value and value.lstrip().lower().startswith("data:") else value


def build_record(
    *,
    request_id: str,
    context_id: str,
    client: dict,
    ctx: SpatialContext,
    image_attached: bool,
    resolution: SemanticResolution,
    answer: str,
    meta: dict,
    timings: dict,
) -> dict[str, Any]:
    candidates = []
    for candidate in ctx.candidates:
        item = candidate.model_dump()
        item["href"], item["src"] = (
            _no_data_url(item["href"]),
            _no_data_url(item["src"]),
        )
        candidates.append(item)
    return {
        "trace_version": TRACE_VERSION,
        "request_id": request_id,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "context_id": context_id,
        "client": client,
        "surface": ctx.surface.model_dump(),
        "privacy_policy": ctx.privacy_policy,
        "image_attached": image_attached,
        "marks": [m.model_dump() for m in ctx.marks],
        "candidates": candidates,
        "resolution": resolution.model_dump(),
        "question": ctx.question,
        "answer": answer,
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "timings_ms": timings,
        "errors": meta.get("errors", {}),
        "cost_usd": meta.get("cost_usd", 0.0),
    }


def _files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.jsonl") if p.is_file())


def _prune(directory: Path) -> None:
    today = datetime.now().date()
    cutoff = today - timedelta(days=settings.trace_retention_days)
    for path in _files(directory):
        try:
            if datetime.strptime(path.stem, "%Y-%m-%d").date() < cutoff:
                path.unlink(missing_ok=True)
        except ValueError:
            continue
    files = _files(directory)
    cap = settings.trace_max_mb * 1024 * 1024
    total = sum(p.stat().st_size for p in files)
    while len(files) > 1 and total > cap:  # oldest first; today's file is always kept
        oldest = files.pop(0)
        total -= oldest.stat().st_size
        oldest.unlink(missing_ok=True)


def write(record: dict[str, Any]) -> None:
    if not enabled():
        return
    try:
        with _lock:
            directory = log_dir()
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            _prune(directory)
    except OSError as exc:
        _state["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("trace log disabled for this process: %s", _state["error"])


def export() -> Iterator[bytes]:
    with _lock:
        paths = _files(log_dir()) if log_dir().is_dir() else []
    for path in paths:
        yield path.read_bytes()


def delete_all() -> int:
    with _lock:
        directory = log_dir()
        paths = _files(directory) if directory.is_dir() else []
        for path in paths:
            path.unlink(missing_ok=True)
    return len(paths)


def status() -> dict[str, Any]:
    directory = log_dir()
    size = sum(p.stat().st_size for p in _files(directory)) if directory.is_dir() else 0
    return {
        "enabled": enabled(),
        "dir": str(directory),
        "size_mb": round(size / 1024 / 1024, 3),
        "error": _state["error"],
    }
