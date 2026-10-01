import os
import sys
from pathlib import Path

os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest

from app import dictations


@pytest.fixture(autouse=True)
def clean():
    dictations.clear()
    yield
    dictations.clear()


def test_fallback_meta_is_short_one_line_and_never_empty():
    title, summary = dictations.fallback_meta(
        "Call Sam tomorrow about the budget review and send the slides.\nThanks"
    )
    assert 0 < len(title) <= 60 and len(title.split()) <= 8 and "\n" not in title
    assert 0 < len(summary) <= 140 and "\n" not in summary
    assert dictations.fallback_meta("   ")[0] == "Dictation"


def test_round_trip_newest_first_update_delete_clear():
    a = dictations.create(
        "first note", "First", "s1", "Notepad", "a.txt", "local", "local cleanup"
    )
    b = dictations.create("second note", "Second", "s2", "", "", "nvidia", "polished")
    assert [e["id"] for e in dictations.list_recent(10)] == [b["id"], a["id"]]
    assert dictations.get(a["id"])["source_app"] == "Notepad"
    edited = dictations.update(
        a["id"], title="Renamed", text="first note, edited", stt_provider="hacked"
    )
    assert edited["title"] == "Renamed" and edited["text"] == "first note, edited"
    assert edited["stt_provider"] == "local"  # only title/summary/text are editable
    assert dictations.update("missing", title="x") is None
    assert dictations.delete(a["id"]) is True and dictations.delete(a["id"]) is False
    assert dictations.clear() == 1 and dictations.list_recent(10) == []


# ---- routes ----
from fastapi.testclient import TestClient

from app import desktop, main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "secret", raising=False)
    monkeypatch.setattr(main.desktop, "token_ok", lambda token: token == "dt", raising=False)
    monkeypatch.setattr(desktop, "window_label", lambda hwnd: {"app": "Notepad", "title": "notes.txt"})
    with TestClient(main.app) as c:
        c.headers.update({"Authorization": "Bearer secret", "X-Spatial-Desktop": "dt"})
        yield c


def test_create_saves_entry_with_fallback_title_and_window_source(client):
    r = client.post("/api/dictations", json={"text": "Call Sam tomorrow about the budget.", "target_hwnd": 77,
                                             "stt_provider": "local", "cleanup_provider": "local cleanup"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] and body["summary"] and body["source_app"] == "Notepad" and body["source_title"] == "notes.txt"
    assert "target_hwnd" not in body
    assert client.get("/api/dictations").json()[0]["id"] == body["id"]


def test_sensitive_window_leaves_source_empty_but_still_saves(client, monkeypatch):
    monkeypatch.setattr(desktop, "window_label", lambda hwnd: {"app": "", "title": ""})
    body = client.post("/api/dictations", json={"text": "secret thing", "target_hwnd": 5}).json()
    assert body["source_app"] == "" and body["source_title"] == ""


def test_blank_and_oversized_text_rejected(client):
    assert client.post("/api/dictations", json={"text": "   "}).status_code == 422
    assert client.post("/api/dictations", json={"text": "x" * 12001}).status_code == 422


def test_requires_token(client):
    anonymous = TestClient(main.app)
    assert anonymous.get("/api/dictations").status_code == 401


def test_patch_delete_and_clear(client):
    a = client.post("/api/dictations", json={"text": "one"}).json()
    client.post("/api/dictations", json={"text": "two"})
    assert client.patch(f"/api/dictations/{a['id']}", json={"title": "Mine", "text": "one!"}).json()["title"] == "Mine"
    assert client.delete(f"/api/dictations/{a['id']}").status_code == 200
    assert client.get(f"/api/dictations/{a['id']}").status_code == 404
    assert client.delete("/api/dictations").json()["deleted"] == 1
    assert client.get("/api/dictations").json() == []


def test_every_dictation_route_needs_the_desktop_token(client):
    a = client.post("/api/dictations", json={"text": "one"}).json()
    web = TestClient(main.app)
    web.headers.update({"Authorization": "Bearer secret"})  # token alone, e.g. a browser extension
    assert web.get("/api/dictations").status_code == 403
    assert web.get(f"/api/dictations/{a['id']}").status_code == 403
    assert web.patch(f"/api/dictations/{a['id']}", json={"title": "x"}).status_code == 403
    assert web.delete(f"/api/dictations/{a['id']}").status_code == 403
    assert web.delete("/api/dictations").status_code == 403


def test_lone_surrogate_text_is_rejected_cleanly_not_a_500(client):
    body = br'{"text": "hi \ud800 there"}'
    assert client.post("/api/dictations", content=body, headers={"Content-Type": "application/json"}).status_code == 422
