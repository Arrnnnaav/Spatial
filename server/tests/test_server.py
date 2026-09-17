import os
import sys
from pathlib import Path

os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
os.environ["SPATIAL_PROVIDERS"] = "nothing"
os.environ["SPATIAL_OCR"] = "0"
os.environ["SPATIAL_API_TOKEN"] = ""
sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient

from app import providers
from app.main import app

PAYLOAD = {
    "question": "What is this?",
    "marks": [{"type": "polygon", "role": "reference", "points": [[100, 100], [300, 100], [300, 200], [100, 200]]}],
    "canvas": {"width": 1280, "height": 720},
    "page": {"url": "https://example.org/anatomy", "title": "Anatomy atlas", "surface": "web"},
    "anchors": [
        {"id": "a1", "type": "img", "text": "Pectoralis major", "bbox": {"x": 90, "y": 90, "width": 220, "height": 120}},
        {"id": "a2", "type": "p", "text": "Unrelated footer", "bbox": {"x": 0, "y": 600, "width": 500, "height": 40}},
    ],
}


def test_health_lists_providers_and_audio():
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert {item["name"] for item in body["providers"]} >= {"ollama", "openrouter", "nvidia", "openai", "anthropic"}
        assert "stt" in body["audio"] and "tts" in body["audio"]


def test_ask_falls_back_to_marked_text_and_keeps_history():
    with TestClient(app) as client:
        first = client.post("/api/ask", json=PAYLOAD)
        assert first.status_code == 200, first.text
        body = first.json()
        assert "Pectoralis major" in body["answer"] and "Unrelated footer" not in body["answer"]
        assert body["provider"] == "none" and body["status"] == "fallback"
        assert body["anchors_used"][0]["id"] == "a1"
        assert body["confidence"] > 0.9
        second = client.post("/api/ask", json={**PAYLOAD, "question": "And which nerve?", "context_id": body["id"]})
        assert second.status_code == 200 and second.json()["id"] == body["id"] and second.json()["turns"] == 2
        listed = client.get("/api/contexts").json()
        assert listed[0]["id"] == body["id"] and listed[0]["page"]["title"] == "Anatomy atlas"
        assert client.get(f"/api/contexts/{body['id']}").json()["answer"]["history"][1]["question"] == "And which nerve?"
        assert client.delete(f"/api/contexts/{body['id']}").status_code == 200
        assert client.get(f"/api/contexts/{body['id']}").status_code == 404


def test_ask_validation():
    with TestClient(app) as client:
        assert client.post("/api/ask", json={"question": "x", "marks": []}).status_code == 400
        assert client.post("/api/ask", json={**PAYLOAD, "context_id": "missing"}).status_code == 404


def test_provider_chain_uses_first_working_provider(monkeypatch):
    from app.config import ProviderConfig
    fake = {"ollama": ProviderConfig("ollama", "http://127.0.0.1:1", None, "m", "v", "ollama"),
            "openrouter": ProviderConfig("openrouter", "https://example", "key", "m2", None, "openai")}
    monkeypatch.setattr(providers.settings, "providers", fake, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("ollama", "openrouter"), raising=False)
    calls = []

    def fake_stream(config, prompt, image_data, use_vision=True):
        calls.append((config.name, use_vision))
        if config.name == "ollama":
            raise RuntimeError("connection refused")
        assert "Pectoralis" in prompt
        yield "It is the "
        yield "pectoralis major."
        yield {"provider": config.name, "model": config.model, "vision": False, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    text, meta = providers.answer("What?", {"title": "t"}, [{"id": "a1", "type": "img", "text": "Pectoralis major"}], "data:image/png;base64,AAAA")
    assert text == "It is the pectoralis major."
    assert meta["provider"] == "openrouter" and meta["status"] == "generated"
    assert meta["errors"]["ollama"]["code"] == providers.ERR_UPSTREAM and "ollama:text" in meta["errors"]
    assert meta["cost_usd"] == 0.0  # unknown/free model
    # ollama tried with vision, then text-only, then openrouter (text-only: no vision model)
    assert calls == [("ollama", True), ("ollama", False), ("openrouter", False)]


def test_partial_stream_failure_keeps_partial_text(monkeypatch):
    from app.config import ProviderConfig
    monkeypatch.setattr(providers.settings, "providers", {"openrouter": ProviderConfig("openrouter", "https://example", "key", "m2", None, "openai")}, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("openrouter",), raising=False)

    def fake_stream(config, prompt, image_data, use_vision=True):
        yield "Half an answer"
        raise RuntimeError("socket closed")

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    text, meta = providers.answer("Q", {}, [], None)
    assert text == "Half an answer" and meta["status"] == "partial"


def test_cost_estimate_and_error_classification():
    assert providers.estimate_cost("gpt-4o-mini", {"prompt_tokens": 1_000_000, "completion_tokens": 0}) == 0.15
    assert providers.estimate_cost("qwen3:4b", {"prompt_tokens": 1000}) == 0.0
    import httpx
    request = httpx.Request("POST", "https://x")
    assert providers.classify_error(httpx.HTTPStatusError("x", request=request, response=httpx.Response(429, request=request)))[0] == providers.ERR_RATE_LIMITED
    assert providers.classify_error(httpx.HTTPStatusError("x", request=request, response=httpx.Response(410, request=request)))[0] == providers.ERR_MODEL_UNAVAILABLE
    assert providers.classify_error(httpx.ConnectTimeout("t"))[0] == providers.ERR_TIMEOUT


def test_stream_emits_status_and_complete():
    with TestClient(app) as client:
        with client.stream("POST", "/api/ask/stream", json=PAYLOAD) as response:
            text = "".join(response.iter_text())
        assert "event: status" in text and "event: complete" in text
        assert '"protocol_version": 2' in text


def test_outdated_client_rejected():
    with TestClient(app) as client:
        response = client.post("/api/ask", json={**PAYLOAD, "protocol_version": 1})
        assert response.status_code == 426 and response.json()["detail"]["code"] == "CLIENT_OUTDATED"


def test_anchors_carry_role_and_mark_index():
    with TestClient(app) as client:
        body = client.post("/api/ask", json={**PAYLOAD, "marks": [
            {"type": "rectangle", "role": "source", "x": 90, "y": 90, "width": 220, "height": 120},
            {"type": "rectangle", "role": "target", "x": 0, "y": 600, "width": 500, "height": 40}]}).json()
        roles = {item["id"]: (item["role"], item["mark_index"]) for item in body["anchors_used"]}
        assert roles["a1"] == ("source", 0) and roles["a2"] == ("target", 1)


def test_token_required_when_configured(monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings, "api_token", "secret", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/contexts").status_code == 401
        assert client.get("/api/contexts", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_clean_answer_strips_leaked_thinking():
    assert providers.clean_answer("<think>\nplan\n</think>\nThe answer.") == "The answer."
    assert providers.clean_answer("plain") == "plain"
