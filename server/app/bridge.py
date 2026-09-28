"""Authenticated, short-lived DOM candidate requests to the paired Chrome extension."""

from __future__ import annotations

import asyncio
import secrets
from uuid import uuid4

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.config import settings


class Bridge:
    def __init__(self) -> None:
        self.socket: WebSocket | None = None
        self.pending: dict[str, asyncio.Future] = {}

    async def serve(self, socket: WebSocket) -> None:
        origin = socket.headers.get("origin", "")
        if not origin.startswith("chrome-extension://") or not settings.api_token:
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            hello = await asyncio.wait_for(socket.receive_json(), timeout=5)
            if not isinstance(hello, dict) or hello.get("type") != "hello" or not secrets.compare_digest(
                str(hello.get("token", "")), settings.api_token
            ):
                await socket.close(code=1008)
                return
            previous = self.socket
            self.socket = socket
            if previous is not None:
                await previous.close(code=1001)
            while True:
                message = await socket.receive_json()
                if isinstance(message, dict) and message.get("type") in {"candidates", "snapshot-ready"}:
                    future = self.pending.get(str(message.get("id", "")))
                    if future is not None and not future.done():
                        future.set_result(message.get("candidates", []) if message["type"] == "candidates"
                                          else message.get("blocked_windows", []))
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, ValueError):
            pass
        finally:
            if self.socket is socket:
                self.socket = None
                for future in self.pending.values():
                    if not future.done():
                        future.set_result(None)

    async def _exchange(self, kind: str, payload: dict, timeout: float):
        socket = self.socket
        if socket is None:
            return None
        request_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await socket.send_json({"type": kind, "id": request_id, **payload})
            return await asyncio.wait_for(future, timeout=timeout)
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            return None
        finally:
            self.pending.pop(request_id, None)

    async def snapshot(self, capture_id: str, windows: list[dict]) -> list[int] | None:
        result = await self._exchange("snapshot", {"capture_id": capture_id, "windows": windows}, 0.8)
        return result if isinstance(result, list) else None

    async def collect(self, capture_id: str, region: dict, monitor: dict, window: dict) -> list[dict] | None:
        result = await self._exchange("collect", {"capture_id": capture_id, "region": region,
                                                  "monitor": monitor,
                                                  "window": {"title": window["title"], "rect": window["rect"]}}, 1.5)
        return result if isinstance(result, list) else None


bridge = Bridge()
