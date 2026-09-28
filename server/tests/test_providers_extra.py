"""Bedrock streaming (stubbed boto3), explain levels, diagram mode."""
import os
import sys
import types
from pathlib import Path

os.environ["SPATIAL_PROVIDERS"] = "nothing"
os.environ["SPATIAL_OCR"] = "0"
sys.path.insert(0, str(Path(__file__).parents[1]))

from app import providers
from app.config import ProviderConfig


class _FakeClient:
    def __init__(self):
        self.calls = []

    def converse_stream(self, **kwargs):
        self.calls.append(kwargs)
        return {"stream": [
            {"contentBlockDelta": {"delta": {"text": "Hello "}}},
            {"contentBlockDelta": {"delta": {"text": "world"}}},
            {"metadata": {"usage": {"inputTokens": 12, "outputTokens": 2}}},
        ]}


def _install_fake_boto3(monkeypatch, client):
    fake = types.ModuleType("boto3")
    fake.client = lambda *a, **k: client
    monkeypatch.setitem(sys.modules, "boto3", fake)
    botocore = types.ModuleType("botocore"); cfg = types.ModuleType("botocore.config")
    cfg.Config = lambda **k: k
    monkeypatch.setitem(sys.modules, "botocore", botocore); monkeypatch.setitem(sys.modules, "botocore.config", cfg)


def test_bedrock_streams_text_and_usage_with_image(monkeypatch):
    client = _FakeClient(); _install_fake_boto3(monkeypatch, client)
    config = ProviderConfig("bedrock", "us-east-1", "1", "amazon.nova-lite-v1:0", "amazon.nova-lite-v1:0", "bedrock")
    assert config.configured
    text, meta = providers.call_provider(config, "What is this?", "data:image/jpeg;base64,/9j/4AAQ", use_vision=True)
    assert text == "Hello world" and meta["model"] == "amazon.nova-lite-v1:0" and meta["vision"] is True
    assert meta["usage"] == {"prompt_tokens": 12, "completion_tokens": 2}
    sent = client.calls[0]
    assert sent["messages"][0]["content"][0]["image"]["format"] == "jpeg" and sent["messages"][0]["content"][1]["text"] == "What is this?"
    assert providers.estimate_cost("amazon.nova-lite-v1:0", meta["usage"]) > 0


def test_bedrock_not_configured_without_flag():
    assert not ProviderConfig("bedrock", "us-east-1", None, "m", None, "bedrock").configured


def test_level_changes_system_prompt_and_is_reported():
    items = list(providers.answer_stream("q", {"title": "t"}, [{"text": "abc"}], None, [], None, [], "eli5"))
    meta = items[-1]
    assert meta["level"] == "eli5" and "10 years old" in providers._system(level="eli5")
    list(providers.answer_stream("q", {"title": "t"}, [{"text": "abc"}], None, [], None, [], "bogus"))
    assert providers._system() == providers.SYSTEM_PROMPT


def test_diagram_mode_when_no_text_but_image():
    items = list(providers.answer_stream("what is drawn?", {"title": "t"}, [{"text": ""}], "data:image/png;base64,iVBORw0KGgo=", [], None, [], None))
    assert items[-1]["diagram"] is True
    prompt = providers.build_prompt("q", {"title": "t", "note": providers.DIAGRAM_NOTE}, [], "", [])
    assert providers.DIAGRAM_NOTE in prompt
    assert list(providers.answer_stream("q", {"title": "t"}, [{"text": "abc"}], "data:image/png;base64,iVBORw0KGgo=", [], None, [], None))[-1]["diagram"] is False
