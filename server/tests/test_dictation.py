import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import desktop, main
from app.desktop import TOKEN_HEADER, session_token
def client():
    return TestClient(main.app, headers={"Authorization": "Bearer test-token", TOKEN_HEADER: session_token()})


def test_polish_is_authenticated_and_text_only(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    seen = {}

    def answer_stream(question, page, anchors, image, **kwargs):
        seen.update(question=question, page=page, anchors=anchors, image=image, kwargs=kwargs)
        yield "Hello, there."
        yield {"status": "generated", "provider": "test-provider"}

    monkeypatch.setattr(main, "answer_stream", answer_stream)
    with TestClient(main.app) as unauthenticated:
        assert unauthenticated.post("/api/dictate/polish", json={"transcript": "hello"}).status_code == 401
    with client() as c:
        response = c.post("/api/dictate/polish", json={"transcript": "hello", "tone": "neutral"})
        assert response.status_code == 200
        assert response.json() == {"text": "Hello, there.", "status": "polished", "backend": "test-provider"}
        assert c.post("/api/dictate/polish", json={"transcript": "x", "audio": "secret"}).status_code == 422
    assert seen["image"] is None and seen["anchors"] == []
    assert seen["kwargs"] == {"prefer_vision": False}


def test_polish_returns_transcript_on_provider_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("provider failure")
        yield  # make this a generator

    monkeypatch.setattr(main, "answer_stream", fail)
    with client() as c:
        response = c.post("/api/dictate/polish", json={"transcript": "  keep my words  "})
    assert response.json() == {"text": "keep my words", "status": "fallback", "backend": "deterministic"}


def test_docx_export_is_authenticated_bounded_and_not_persisted():
    from zipfile import ZipFile
    from io import BytesIO

    with TestClient(main.app) as unauthenticated:
        assert unauthenticated.post("/api/dictate/docx", json={"text": "hello"}).status_code == 403
    with client() as c:
        response = c.post("/api/dictate/docx", json={"text": "To-do list:\n- first\n- second"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with ZipFile(BytesIO(response.content)) as docx:
            content = docx.read("word/document.xml").decode()
            assert "To-do list:" in content and "• </w:t>" in content and ">first</w:t>" in content and ">second</w:t>" in content
        assert c.post("/api/dictate/docx", json={"text": "x" * 12001}).status_code == 422
        assert c.post("/api/dictate/docx", json={"text": "hello", "audio": "private"}).status_code == 422


def test_focus_safety_requires_both_tokens_and_returns_only_safety(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "test-token")
    monkeypatch.setattr(main.desktop, "dictation_target_safe", lambda hwnd: (False, "focus_changed"))
    with client() as c:
        response = c.post("/api/desktop/dictation-safe", json={"target_hwnd": 42})
        assert response.status_code == 200
        assert response.json() == {"safe": False, "reason": "focus_changed"}
        assert c.post("/api/desktop/dictation-safe", json={"target_hwnd": 42}, headers={"X-Spatial-Desktop": "bad"}).status_code == 403


def test_focus_safety_allows_only_editable_nonpassword_field(monkeypatch):
    class Focus:
        CurrentIsPassword = False
        CurrentIsEnabled = True
        CurrentIsKeyboardFocusable = True
        CurrentProcessId = 7
        CurrentNativeWindowHandle = 42
        CurrentControlType = 50004

        def GetCurrentPattern(self, pattern):
            return SimpleNamespace(CurrentIsReadOnly=False)

    focus = Focus()
    monkeypatch.setattr(desktop, "SUPPORTED", True)
    monkeypatch.setattr(desktop, "_windows_topdown", lambda: [{"hwnd": 42, "pid": 7, "process": "notepad.exe", "title": "Untitled - Notepad"}])
    monkeypatch.setattr(desktop, "_uia_client", lambda: (SimpleNamespace(GetFocusedElement=lambda: focus), SimpleNamespace(UIA_EditControlTypeId=50004, UIA_DocumentControlTypeId=50030, UIA_ValuePatternId=10002, UIA_TextPatternId=10014)))
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(GetForegroundWindow=lambda: 42))
    monkeypatch.setitem(sys.modules, "win32process", SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (1, 7)))
    assert desktop.dictation_target_safe(42) == (True, "safe")
    focus.CurrentControlType = 50000
    assert desktop.dictation_target_safe(42) == (False, "unsupported_field")
    focus.CurrentControlType = 50004
    focus.CurrentIsPassword = True
    assert desktop.dictation_target_safe(42) == (False, "protected_field")
