import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import main, personal


@pytest.fixture(autouse=True)
def clean():
    personal.clear_all()
    yield
    personal.clear_all()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "secret", raising=False)
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "dt", raising=False
    )
    with TestClient(main.app) as c:
        c.headers.update({"Authorization": "Bearer secret", "X-Spatial-Desktop": "dt"})
        yield c


def iso(delta_seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def test_task_crud(client):
    t = client.post("/api/tasks", json={"text": "Buy milk", "note": "2 litres"}).json()
    assert t["done"] is False and t["note"] == "2 litres"
    done = client.patch(f"/api/tasks/{t['id']}", json={"done": True}).json()
    assert done["done"] is True and done["done_at"]
    assert [x["id"] for x in client.get("/api/tasks").json()] == [t["id"]]
    assert client.delete(f"/api/tasks/{t['id']}").status_code == 200
    assert client.delete(f"/api/tasks/{t['id']}").status_code == 404


def test_reminder_needs_timezone_and_valid_text(client):
    assert (
        client.post(
            "/api/reminders", json={"text": "x", "due_at": "2026-10-01T10:00:00"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/reminders", json={"text": "x", "due_at": "garbage"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/reminders", json={"text": "  ", "due_at": iso(60)}
        ).status_code
        == 422
    )


def test_due_lists_only_past_unfired_and_firing_is_idempotent(client):
    past = client.post(
        "/api/reminders", json={"text": "late", "due_at": iso(-3600)}
    ).json()
    future = client.post(
        "/api/reminders", json={"text": "later", "due_at": iso(3600)}
    ).json()
    due = client.get("/api/reminders/due").json()
    assert [r["id"] for r in due] == [past["id"]]
    assert client.post(f"/api/reminders/{past['id']}/fired").status_code == 200
    assert client.post(f"/api/reminders/{past['id']}/fired").status_code == 200
    assert client.get("/api/reminders/due").json() == []
    assert future["id"] in [r["id"] for r in client.get("/api/reminders").json()]


def test_reminder_keeps_its_text_when_the_task_is_deleted(client):
    t = client.post("/api/tasks", json={"text": "Call Sam"}).json()
    r = client.post(
        "/api/reminders",
        json={"text": "Call Sam", "due_at": iso(60), "task_id": t["id"]},
    ).json()
    client.delete(f"/api/tasks/{t['id']}")
    assert [
        x["text"] for x in client.get("/api/reminders").json() if x["id"] == r["id"]
    ] == ["Call Sam"]


def test_all_routes_need_both_tokens(client):
    web = TestClient(main.app)
    web.headers.update({"Authorization": "Bearer secret"})
    for method, path in [
        ("get", "/api/tasks"),
        ("get", "/api/reminders"),
        ("get", "/api/reminders/due"),
        ("post", "/api/tasks"),
        ("post", "/api/reminders"),
    ]:
        assert getattr(web, method)(path).status_code in (403, 422), path
    assert web.get("/api/tasks").status_code == 403
    assert web.get("/api/reminders/due").status_code == 403
