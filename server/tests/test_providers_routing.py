import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import providers  # noqa: E402
from app.config import ProviderConfig  # noqa: E402

ANCHORS = [
    {"id": "t", "type": "button", "text": "Edit", "is_target": True},
    {"id": "n", "type": "div", "text": "File Edit View"},
]


def test_prompt_puts_target_first():
    prompt = providers.build_prompt(
        "what does this do?", {"title": "App"}, ANCHORS, "", []
    )
    assert "The user is asking about:\n- [button] Edit" in prompt
    assert "Nearby, probably not the target:\n- [div] File Edit View" in prompt


def test_prompt_without_target_unchanged():
    prompt = providers.build_prompt("q", {"title": "App"}, [dict(ANCHORS[1])], "", [])
    assert "Text under the mark (ranked, most relevant first):" in prompt


def run(monkeypatch, **kwargs):
    fake = {
        "p": ProviderConfig(
            "p", "https://example", "key", "text-model", "vision-model", "openai"
        )
    }
    monkeypatch.setattr(providers.settings, "providers", fake, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("p",), raising=False)
    calls = []

    def fake_stream(config, prompt, image_data, use_vision=True):
        calls.append((use_vision, providers._system()))
        yield "ok"
        yield {"provider": "p", "model": "m", "vision": use_vision}

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    items = list(
        providers.answer_stream(
            "q", {"title": "t"}, ANCHORS, "data:image/png;base64,AAAA", **kwargs
        )
    )
    return calls, items[-1]


def test_prefer_vision_false_skips_vision(monkeypatch):
    calls, meta = run(monkeypatch, prefer_vision=False, precomputed_ocr="")
    assert [c[0] for c in calls] == [False]
    calls, _ = run(monkeypatch, prefer_vision=None, precomputed_ocr="")
    assert [c[0] for c in calls] == [True]


def test_mode_adds_hint_to_system_prompt(monkeypatch):
    calls, meta = run(monkeypatch, mode="define", precomputed_ocr="")
    assert providers.MODE_HINTS["define"] in calls[0][1] and meta["mode"] == "define"
    calls, meta = run(monkeypatch, mode="bogus", precomputed_ocr="")
    assert (
        not any(h in calls[0][1] for h in providers.MODE_HINTS.values() if h)
        and meta["mode"] is None
    )


def test_diagram_keeps_vision_even_if_routing_says_not_visual(monkeypatch):
    global ANCHORS
    saved = ANCHORS
    ANCHORS = [{"id": "img", "type": "img", "text": ""}]
    try:
        calls, _ = run(monkeypatch, prefer_vision=False, precomputed_ocr="")
    finally:
        ANCHORS = saved
    assert calls[0][0] is True
