"""Transport to a System One endpoint (TypeSafe Jev today; Laya later via base URL + model).
One kept-alive client (TLS setup from India costs ~1 s; a warm call ~0.5 s), a hard time budget, one retry on
429/5xx inside that budget. Knows nothing about Spatial; never logs or returns the key."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("spatial.system_one")
_lock = threading.Lock()
_client: httpx.Client | None = None
_transport: httpx.BaseTransport | None = None
_last = {"status": "unknown"}


@dataclass
class Result:
    status: str  # ok | off | timeout | error | rate_limited | auth_failed
    answers: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    latency_ms: int = 0
    input_tokens: int = 0


def enabled() -> bool:
    return settings.system_one_backend == "jev" and bool(settings.typesafe_api_key)


def _client_get() -> httpx.Client:
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(
                base_url=settings.typesafe_base_url,
                transport=_transport,
                headers={"Authorization": f"Bearer {settings.typesafe_api_key}"},
                timeout=settings.system_one_timeout,
            )
        return _client


def reset(transport: httpx.BaseTransport | None = None) -> None:
    """Drop the client (tests, key change). A transport given here is used by the next client."""
    global _client, _transport
    with _lock:
        if _client is not None:
            _client.close()
        _client, _transport = None, transport


def _done(result: Result) -> Result:
    _last["status"] = result.status
    return result


def evaluate(state: Any, questions: dict[str, Any]) -> Result:
    if not enabled():
        return _done(Result("off"))
    body = {"model": settings.typesafe_model, "state": state, "questions": questions}
    started = time.perf_counter()
    deadline = started + settings.system_one_timeout

    def elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    for attempt in (1, 2):
        remaining = deadline - time.perf_counter()
        if remaining <= 0.05:
            return _done(Result("timeout", latency_ms=elapsed()))
        try:
            response = _client_get().post("/v1/systemone", json=body, timeout=remaining)
        except httpx.TimeoutException:
            return _done(Result("timeout", latency_ms=elapsed()))
        except httpx.HTTPError as exc:
            logger.warning("system one request failed: %s", type(exc).__name__)
            return _done(Result("error", latency_ms=elapsed()))
        code = response.status_code
        if code in (401, 403):
            return _done(Result("auth_failed", latency_ms=elapsed()))
        if code == 429 or code >= 500:
            if attempt == 1:
                continue
            return _done(
                Result("rate_limited" if code == 429 else "error", latency_ms=elapsed())
            )
        if code >= 400:
            return _done(Result("error", latency_ms=elapsed()))
        try:
            data = response.json()
        except ValueError:
            return _done(Result("error", latency_ms=elapsed()))
        return _done(
            Result(
                "ok",
                data.get("answers") or {},
                data.get("model"),
                elapsed(),
                int((data.get("usage") or {}).get("input_tokens", 0)),
            )
        )
    return _done(Result("error", latency_ms=elapsed()))


def warm() -> None:
    """Open the TLS connection before the first ask. Failures only log."""
    if not enabled():
        return
    try:
        _client_get().get("/", timeout=settings.system_one_timeout)
    except httpx.HTTPError as exc:
        logger.info("system one warm-up failed: %s", type(exc).__name__)


def status() -> dict[str, Any]:
    return {
        "backend": settings.system_one_backend if enabled() else "off",
        "model": settings.typesafe_model if enabled() else None,
        "last_status": _last["status"],
    }
