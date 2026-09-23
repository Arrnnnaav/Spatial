import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import desktop, main  # noqa: E402

MONITOR = {"x": 0, "y": 0, "width": 1920, "height": 1080}
OVERLAY = {
    "hwnd": 11,
    "pid": 900,
    "process": "SpatialDesktop.exe",
    "title": "Spatial overlay",
    "rect": (0, 0, 1920, 1080),
}
CODE = {
    "hwnd": 22,
    "pid": 100,
    "process": "Code.exe",
    "title": "notes.md - Visual Studio Code",
    "rect": (100, 50, 1500, 900),
}
KEEPASS = {
    "hwnd": 33,
    "pid": 200,
    "process": "KeePass.exe",
    "title": "Vault - bank.kdbx",
    "rect": (0, 0, 800, 600),
}
ELEMENTS = {
    22: [
        {
            "type": "Button",
            "text": "Run",
            "bbox": {"x": 300, "y": 200, "width": 60, "height": 24},
        },
        {
            "type": "TextLine",
            "text": "def area(r): return 3.14 * r * r",
            "bbox": {"x": 320, "y": 260, "width": 400, "height": 20},
        },
        {
            "type": "Button",
            "text": "Far away",
            "bbox": {"x": 1300, "y": 800, "width": 60, "height": 24},
        },
    ],
    33: [
        {
            "type": "Edit",
            "text": "hunter2",
            "bbox": {"x": 300, "y": 200, "width": 100, "height": 20},
        }
    ],
}
REGION = {"x": 280, "y": 180, "width": 500, "height": 120}


@pytest.fixture
def fake_os(monkeypatch):
    """Returns (reads, set_windows): UIA reads by hwnd, and a setter for the z-order the next capture sees."""
    monkeypatch.setattr(desktop, "SUPPORTED", True)
    monkeypatch.setattr(
        desktop,
        "_grab_monitor",
        lambda: (Image.new("RGB", (1920, 1080), "white"), dict(MONITOR)),
    )
    windows = {"list": [OVERLAY, CODE, KEEPASS]}
    monkeypatch.setattr(
        desktop, "_windows_topdown", lambda: [dict(w) for w in windows["list"]]
    )
    reads = []

    def reader(hwnd, region, pid=None):
        reads.append(hwnd)
        return list(ELEMENTS.get(hwnd, []))

    monkeypatch.setattr(desktop, "_uia_read", reader)
    monkeypatch.setattr(desktop, "ocr_blocks", lambda image_data: [])
    desktop._captures.clear()
    return reads, lambda new: windows.__setitem__("list", new)


def client() -> TestClient:
    return TestClient(main.app, headers={desktop.TOKEN_HEADER: desktop.session_token()})


def candidates(c, region=REGION, exclude=(900,)):
    cap = c.post("/api/desktop/capture", json={}).json()
    return cap, c.post(
        "/api/desktop/candidates",
        json={
            "capture_id": cap["capture_id"],
            "region": region,
            "exclude_pids": list(exclude),
        },
    ).json()


def v3_ask(capture_id, bbox=REGION):
    return {
        "protocol_version": 3,
        "capture_id": capture_id,
        "context": {
            "surface": {
                "kind": "desktop",
                "app": "Code",
                "viewport": {"width": 1920, "height": 1080},
            },
            "marks": [{"kind": "rectangle", "bbox": bbox}],
            "candidates": [],
            "question": "what is this?",
            "privacy_policy": "crop_only",
        },
    }


def test_capture_returns_frame_and_id(fake_os):
    with client() as c:
        body = c.post("/api/desktop/capture", json={}).json()
    assert body["capture_id"] and body["monitor"] == MONITOR
    assert body["image_data"].startswith("data:image/jpeg;base64,")


def test_candidates_from_topmost_window_excluding_overlay(fake_os):
    reads, _ = fake_os
    with client() as c:
        _, body = candidates(c)
    assert [c["text"] for c in body["candidates"]] == [
        "Run",
        "def area(r): return 3.14 * r * r",
    ]  # far one dropped
    assert all(c["source"] == "uia" for c in body["candidates"])
    # Code covers the whole region, so KeePass below it is neither read nor judged.
    assert reads == [22] and body["window"] == {
        "app": "Visual Studio Code",
        "process": "Code.exe",
        "title": "notes.md - Visual Studio Code",
    }


def test_sensitive_window_on_top_is_never_read_and_title_hidden(fake_os):
    reads, set_windows = fake_os
    set_windows([OVERLAY, KEEPASS, CODE])
    with client() as c:
        cap, body = candidates(c)
        ask = c.post("/api/ask", json=v3_ask(cap["capture_id"])).json()
    assert reads == [] and body["candidates"] == []
    assert body["window"]["sensitive"] is True and body["window"]["title"] == ""
    assert (
        ask["resolution"]["image_attached"] is False
    )  # no crop of the vault goes to the model


def test_partly_covering_window_does_not_hide_sensitive_one_below(fake_os, monkeypatch):
    reads, set_windows = fake_os
    small = {
        "hwnd": 44,
        "pid": 300,
        "process": "notepad.exe",
        "title": "a.txt - Notepad",
        "rect": (250, 150, 400, 250),
    }
    set_windows([small, KEEPASS])
    ocr_calls = []
    monkeypatch.setattr(
        desktop, "ocr_blocks", lambda image_data: ocr_calls.append(1) or []
    )
    monkeypatch.setattr(desktop.settings, "ocr_enabled", True)
    with client() as c:
        _, body = candidates(c, exclude=())
    assert body["window"].get("sensitive") is True and reads == [] and ocr_calls == []


@pytest.mark.parametrize(
    "window",
    [
        {
            "hwnd": 55,
            "pid": 400,
            "process": "",
            "title": "Admin tool",
            "rect": (0, 0, 1920, 1080),
        },  # unreadable process
        {
            "hwnd": 56,
            "pid": 401,
            "process": "vault-portable.exe",
            "title": "Bitwarden",
            "rect": (0, 0, 1920, 1080),
        },
    ],
)
def test_unknown_process_or_manager_title_fails_closed(fake_os, window):
    reads, set_windows = fake_os
    set_windows([window])
    with client() as c:
        _, body = candidates(c, exclude=())
    assert reads == [] and body["window"]["sensitive"] is True


def test_desktop_routes_need_the_desktop_token(fake_os):
    with TestClient(main.app) as c:
        capture = c.post("/api/desktop/capture", json={})
        ask = c.post("/api/ask", json=v3_ask("anything"))
    assert (
        capture.status_code == 403
        and capture.json()["detail"]["code"] == "DESKTOP_TOKEN"
    )
    assert ask.status_code == 403


def test_foreign_host_header_is_rejected():
    with TestClient(main.app, base_url="http://attacker.example") as c:
        assert c.get("/api/health").status_code == 400


def test_non_finite_region_is_422(fake_os):
    with client() as c:
        cap = c.post("/api/desktop/capture", json={}).json()
        r = c.post(
            "/api/desktop/candidates",
            content='{"capture_id": "%s", "region": {"x": Infinity, "y": 0, "width": 5, "height": 5}}'
            % cap["capture_id"],
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 422


def test_unknown_capture_is_404(fake_os):
    with client() as c:
        r = c.post(
            "/api/desktop/candidates",
            json={
                "capture_id": "nope",
                "region": {"x": 0, "y": 0, "width": 5, "height": 5},
            },
        )
    assert r.status_code == 404 and r.json()["detail"]["code"] == "CAPTURE_NOT_FOUND"


def test_unsupported_platform_is_501(monkeypatch):
    monkeypatch.setattr(desktop, "SUPPORTED", False)
    with client() as c:
        r = c.post("/api/desktop/capture", json={})
    assert r.status_code == 501 and r.json()["detail"]["code"] == "DESKTOP_UNSUPPORTED"


def test_captures_are_bounded_and_expire(fake_os, monkeypatch):
    with client() as c:
        ids = [
            c.post("/api/desktop/capture", json={}).json()["capture_id"]
            for _ in range(5)
        ]
        assert list(desktop._captures) == ids[-desktop.MAX_CAPTURES :]
        monkeypatch.setattr(desktop, "CAPTURE_TTL_SECONDS", -1)
        c.post("/api/desktop/capture", json={})  # sweeps every expired frame
    assert len(desktop._captures) == 1


def test_ask_with_capture_id_attaches_crop_server_side(fake_os):
    with client() as c:
        cap = c.post("/api/desktop/capture", json={}).json()
        body = c.post("/api/ask", json=v3_ask(cap["capture_id"])).json()
    assert body["resolution"]["image_attached"] is True


def test_ocr_is_fallback_only_when_uia_finds_nothing(fake_os, monkeypatch):
    calls = []

    def fake_ocr(image_data):
        calls.append(1)
        return [
            {
                "text": "Canvas label",
                "confidence": 0.9,
                "bbox": {"x": 30, "y": 30, "width": 80, "height": 20},
            }
        ]

    monkeypatch.setattr(desktop, "ocr_blocks", fake_ocr)
    monkeypatch.setattr(desktop.settings, "ocr_enabled", True)
    with client() as c:
        _, with_uia = candidates(c)
        assert calls == [] and all(c["source"] == "uia" for c in with_uia["candidates"])
        _, empty_area = candidates(
            c, region={"x": 900, "y": 400, "width": 200, "height": 100}
        )
    assert calls == [1] and [c["text"] for c in empty_area["candidates"]] == [
        "Canvas label"
    ]


def test_tauri_origin_allowed_by_cors():
    with TestClient(main.app) as c:
        r = c.get("/api/health", headers={"Origin": "http://tauri.localhost"})
    assert r.headers.get("access-control-allow-origin") == "http://tauri.localhost"
