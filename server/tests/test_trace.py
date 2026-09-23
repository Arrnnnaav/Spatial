import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("SPATIAL_DB", str(Path(__file__).parent / "test_spatial.db"))
os.environ.setdefault("SPATIAL_PROVIDERS", "nothing")
os.environ.setdefault("SPATIAL_OCR", "0")
os.environ.setdefault("SPATIAL_API_TOKEN", "")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main, trace  # noqa: E402
from tests.test_server import PAYLOAD  # noqa: E402

BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{200,}")


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(trace.settings, "trace_dir", str(tmp_path))
    monkeypatch.setattr(trace.settings, "trace_enabled", False)
    monkeypatch.setattr(trace.settings, "trace_max_mb", 50.0)
    monkeypatch.setattr(trace.settings, "trace_retention_days", 14)
    trace._state["error"] = None
    return tmp_path


def lines(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for f in sorted(directory.glob("*.jsonl"))
        for line in f.read_text(encoding="utf-8").splitlines()
    ]


def test_off_by_default_writes_nothing(log_dir):
    with TestClient(main.app) as client:
        client.post("/api/ask", json=PAYLOAD)
    assert list(log_dir.glob("*.jsonl")) == []


def test_on_writes_one_line_per_ask_without_images(log_dir):
    image = "data:image/jpeg;base64," + "A" * 5000
    anchors = [
        *PAYLOAD["anchors"],
        {
            "id": "inline",
            "type": "img",
            "text": "",
            "src": "data:image/png;base64," + "B" * 400,
            "bbox": {"x": 95, "y": 95, "width": 50, "height": 50},
        },
    ]
    with TestClient(main.app) as client:
        assert (
            client.put("/api/traces/config", json={"enabled": True}).json()["enabled"]
            is True
        )
        client.post(
            "/api/ask", json={**PAYLOAD, "anchors": anchors, "image_data": image}
        )
        client.post("/api/ask", json=PAYLOAD)
    records = lines(log_dir)
    assert len(records) == 2
    first = records[0]
    assert (
        first["trace_version"] == 1
        and first["question"] == "What is this?"
        and first["image_attached"] is True
    )
    assert first["resolution"]["selected_candidate_id"] == "a1"
    assert {"resolve", "research", "answer", "total"} <= set(first["timings_ms"])
    raw = "".join(f.read_text(encoding="utf-8") for f in log_dir.glob("*.jsonl"))
    assert "data:image" not in raw and not BASE64_RUN.search(raw)
    assert "image_data" not in raw


def test_config_persists_in_log_dir(log_dir):
    trace.set_enabled(True)
    assert json.loads((log_dir / "config.json").read_text()) == {"enabled": True}
    assert trace.enabled() is True
    trace.set_enabled(False)
    assert trace.enabled() is False


def test_retention_and_size_cap(log_dir, monkeypatch):
    old = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    mid = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    (log_dir / f"{old}.jsonl").write_text("{}\n")
    (log_dir / f"{mid}.jsonl").write_text("x" * 2_000_000)
    monkeypatch.setattr(trace.settings, "trace_max_mb", 1.0)
    trace.set_enabled(True)
    trace.write({"trace_version": 1})
    names = sorted(p.name for p in log_dir.glob("*.jsonl"))
    assert names == [datetime.now().strftime("%Y-%m-%d") + ".jsonl"]


def test_export_and_delete(log_dir):
    trace.set_enabled(True)
    trace.write({"n": 1})
    with TestClient(main.app) as client:
        exported = client.get("/api/traces/export")
        assert exported.status_code == 200 and json.loads(
            exported.text.splitlines()[0]
        ) == {"n": 1}
        assert client.delete("/api/traces").json() == {"deleted_files": 1}
    assert list(log_dir.glob("*.jsonl")) == []


def test_unwritable_dir_never_fails_the_ask(log_dir, monkeypatch):
    blocker = log_dir / "blocked"
    blocker.write_text("i am a file, not a directory")
    monkeypatch.setattr(trace.settings, "trace_dir", str(blocker))
    monkeypatch.setattr(trace.settings, "trace_enabled", True)
    with TestClient(main.app) as client:
        assert client.post("/api/ask", json=PAYLOAD).status_code == 200
        health = client.get("/api/health").json()
    assert health["trace"]["enabled"] is False and health["trace"]["error"]


def test_lone_surrogate_in_anchor_text_does_not_fail_the_ask(log_dir):
    anchors = [{**PAYLOAD["anchors"][0], "text": "Pectoralis major \ud83d"}, PAYLOAD["anchors"][1]]
    trace.set_enabled(True)
    with TestClient(main.app) as client:
        # Browsers send JSON with the lone surrogate escaped as \ud83d; post the same bytes.
        body = json.dumps({**PAYLOAD, "anchors": anchors})
        response = client.post("/api/ask", content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 200
    assert len(lines(log_dir)) == 1


def test_data_urls_in_any_v3_field_never_reach_the_trace(log_dir):
    from tests.test_protocol import V3
    icon = "data:image/png;base64," + "C" * 300
    context = {**V3["context"], "surface": {**V3["context"]["surface"], "url": icon}}
    context["candidates"] = [{**context["candidates"][0], "label": icon, "attributes": {"icon": icon},
                              "src": icon}, context["candidates"][1]]
    trace.set_enabled(True)
    with TestClient(main.app) as client:
        assert client.post("/api/ask", json={**V3, "context": context}).status_code == 200
    raw = "".join(f.read_text(encoding="utf-8") for f in log_dir.glob("*.jsonl"))
    assert raw and "data:image" not in raw and not BASE64_RUN.search(raw)


def test_cors_only_allows_extension_origins():
    with TestClient(main.app) as client:
        evil = client.get("/api/traces/config", headers={"Origin": "https://evil.example"})
        ext = client.get("/api/traces/config", headers={"Origin": "chrome-extension://abcdefghijklmnop"})
    assert "access-control-allow-origin" not in evil.headers
    assert ext.headers.get("access-control-allow-origin") == "chrome-extension://abcdefghijklmnop"
