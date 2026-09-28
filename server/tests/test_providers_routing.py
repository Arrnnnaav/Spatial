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

    def fake_stream(config, prompt, image_data, use_vision=True, system_prompt=None):
        calls.append((use_vision, system_prompt))
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


def test_interleaved_asks_keep_their_own_system_prompts(monkeypatch):
    fake = {"p": ProviderConfig("p", "https://example", "key", "m", None, "openai")}
    monkeypatch.setattr(providers.settings, "providers", fake, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("p",), raising=False)
    sent = []

    def fake_stream(config, prompt, image_data, use_vision=True, system_prompt=None):
        sent.append(system_prompt)
        yield "answer"
        yield {"provider": "p", "model": "m", "vision": False}

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    first = providers.answer_stream("q1", {}, ANCHORS, None, level="eli5", mode="define")
    second = providers.answer_stream("q2", {}, ANCHORS, None, level="expert", mode="compare")
    next(first)
    next(second)
    assert "10 years old" in sent[0] and "meaning" in sent[0]
    assert "expert" in sent[1] and "Compare" in sent[1]


def test_diagram_keeps_vision_even_if_routing_says_not_visual(monkeypatch):
    global ANCHORS
    saved = ANCHORS
    ANCHORS = [{"id": "img", "type": "img", "text": ""}]
    try:
        calls, _ = run(monkeypatch, prefer_vision=False, precomputed_ocr="")
    finally:
        ANCHORS = saved
    assert calls[0][0] is True


def run_flaky(monkeypatch, failures, error=503, fallbacks=()):
    import httpx
    fake = {"p": ProviderConfig("p", "https://example", "key", "main-model", None, "openai", tuple(fallbacks))}
    monkeypatch.setattr(providers.settings, "providers", fake, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("p",), raising=False)
    monkeypatch.setattr(providers, "RETRY_DELAY", 0.0)
    calls = []

    def fake_stream(config, prompt, image_data, use_vision=True, system_prompt=None):
        calls.append(config.model)
        if len(calls) <= failures:
            request = httpx.Request("POST", "https://example/chat/completions")
            if error == "timeout":
                raise httpx.ReadTimeout("slow", request=request)
            raise httpx.HTTPStatusError("busy", request=request, response=httpx.Response(error, request=request))
        yield "answer"
        yield {"provider": "p", "model": config.model, "vision": False}

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    items = list(providers.answer_stream("q", {"title": "t"}, [{"id": "a", "type": "p", "text": "x"}], None))
    return calls, items[-1]


def test_busy_is_retried_up_to_three_attempts(monkeypatch):
    calls, meta = run_flaky(monkeypatch, failures=2)
    assert calls == ["main-model"] * 3 and meta["status"] == "generated"


def test_three_busy_attempts_then_falls_through(monkeypatch):
    calls, meta = run_flaky(monkeypatch, failures=3)
    assert calls == ["main-model"] * 3 and meta["status"] == "fallback"


def test_busy_three_times_moves_to_fallback_model(monkeypatch):
    calls, meta = run_flaky(monkeypatch, failures=3, fallbacks=("backup-model",))
    assert calls == ["main-model"] * 3 + ["backup-model"] and meta["model"] == "backup-model"


def test_timeout_skips_straight_to_fallback_model(monkeypatch):
    calls, meta = run_flaky(monkeypatch, failures=1, error="timeout", fallbacks=("backup-model",))
    assert calls == ["main-model", "backup-model"] and meta["status"] == "generated"


def test_auth_error_is_not_retried(monkeypatch):
    calls, meta = run_flaky(monkeypatch, failures=5, error=401, fallbacks=("backup-model",))
    assert calls == ["main-model"] and meta["status"] == "fallback"


def test_empty_answer_counts_as_busy_and_is_retried(monkeypatch):
    fake = {"p": ProviderConfig("p", "https://example", "key", "main-model", None, "openai", ("backup-model",))}
    monkeypatch.setattr(providers.settings, "providers", fake, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("p",), raising=False)
    monkeypatch.setattr(providers, "RETRY_DELAY", 0.0)
    calls = []

    def fake_stream(config, prompt, image_data, use_vision=True, system_prompt=None):
        calls.append(config.model)
        if len(calls) <= 3:  # main model returns nothing three times
            yield {"provider": "p", "model": config.model, "vision": False}
            return
        yield "real answer"
        yield {"provider": "p", "model": config.model, "vision": False}

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    items = list(providers.answer_stream("q", {"title": "t"}, [{"id": "a", "type": "p", "text": "x"}], None))
    assert calls == ["main-model"] * 3 + ["backup-model"]
    assert "real answer" in items and items[-1]["model"] == "backup-model"
