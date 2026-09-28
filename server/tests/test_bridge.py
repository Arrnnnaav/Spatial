"""The bridge accepts only a paired extension and correlates one DOM reply with one mark."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import bridge  # noqa: E402


class Socket:
    headers = {"origin": "chrome-extension://test"}

    def __init__(self, token):
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait({"type": "hello", "token": token})
        self.closed = None

    async def accept(self):
        pass

    async def close(self, code):
        self.closed = code

    async def receive_json(self):
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send_json(self, message):
        if message["type"] == "snapshot":
            self.incoming.put_nowait({"type": "snapshot-ready", "id": message["id"]})
        else:
            self.incoming.put_nowait({"type": "candidates", "id": message["id"],
                                      "candidates": [{"text": "Page heading"}]})


def test_bridge_auth_and_correlated_reply(monkeypatch):
    monkeypatch.setattr(bridge.settings, "api_token", "paired-secret")

    async def check():
        channel = bridge.Bridge()
        rejected = Socket("wrong")
        await channel.serve(rejected)
        assert rejected.closed == 1008 and channel.socket is None

        accepted = Socket("paired-secret")
        task = asyncio.create_task(channel.serve(accepted))
        for _ in range(10):
            if channel.socket is accepted:
                break
            await asyncio.sleep(0)
        await channel.snapshot("capture", [{"title": "Chrome", "rect": [0, 0, 10, 10]}])
        result = await channel.collect("capture", {"x": 1}, {"x": 0}, {"title": "Chrome", "rect": [0, 0, 10, 10]})
        assert result == [{"text": "Page heading"}]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert channel.socket is None and channel.pending == {}

    asyncio.run(check())
