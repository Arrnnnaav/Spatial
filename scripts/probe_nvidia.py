"""List which NVIDIA NIM chat models actually answer for your key (free accounts get a subset).

    python scripts/probe_nvidia.py
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from app.config import settings  # noqa: E402  (loads server/.env)

import httpx  # noqa: E402

key = settings.providers["nvidia"].api_key or os.environ.get("NVIDIA_API_KEY")
if not key:
    sys.exit("NVIDIA_API_KEY not set in server/.env")
H = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
BASE = settings.providers["nvidia"].base_url.rstrip("/")
SKIP = ("embed", "reward", "safety", "guard", "rerank", "parse", "retriever", "diffusion")
ids = [m["id"] for m in httpx.get(f"{BASE}/models", headers=H, timeout=30).json()["data"] if not any(s in m["id"] for s in SKIP)]


def probe(model: str):
    try:
        r = httpx.post(f"{BASE}/chat/completions", headers=H, timeout=60, json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 3})
        return model, r.status_code, "ok" if "choices" in r.json() else r.text[:70]
    except Exception as exc:
        return model, 0, str(exc)[:70]


with cf.ThreadPoolExecutor(8) as pool:
    for model, code, note in pool.map(probe, ids):
        print(("OK   " if code == 200 else f"{code:<5}"), model, "" if code == 200 else note)
