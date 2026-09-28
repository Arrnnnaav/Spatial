import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import system_one  # noqa: E402

ANSWERS = {
    "target": {
        "type": "choice",
        "choice": "A",
        "confidence": 0.9,
        "probabilities": {"A": 0.95, "none": 0.05},
    }
}


@pytest.fixture
def jev(monkeypatch):
    monkeypatch.setattr(system_one.settings, "system_one_backend", "jev")
    monkeypatch.setattr(system_one.settings, "typesafe_api_key", "test-key-123")
    monkeypatch.setattr(system_one.settings, "system_one_timeout", 0.5)
    yield
    system_one.reset()


def install(handler):
    system_one.reset(httpx.MockTransport(handler))


def test_off_without_key_makes_no_request(monkeypatch):
    monkeypatch.setattr(system_one.settings, "system_one_backend", "off")
    calls = []
    install(lambda request: calls.append(request) or httpx.Response(200, json={}))
    assert system_one.evaluate({"q": 1}, {}).status == "off"
    assert calls == []
    system_one.reset()


def test_ok_sends_auth_model_and_parses(jev):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": ANSWERS,
                "usage": {"input_tokens": 321},
            },
        )

    install(handler)
    result = system_one.evaluate({"q": 1}, {"target": {"type": "choice"}})
    assert (
        result.status == "ok"
        and result.answers == ANSWERS
        and result.model == "jev-1.13.0"
    )
    assert (
        result.input_tokens == 321
        and seen["auth"] == "Bearer test-key-123"
        and seen["path"] == "/v1/systemone"
    )
    assert (
        b'"model": "jev-latest"' in seen["body"]
        or b'"model":"jev-latest"' in seen["body"]
    )


def test_429_retried_once_then_ok(jev):
    replies = [httpx.Response(429), httpx.Response(200, json={"answers": ANSWERS})]
    install(lambda request: replies.pop(0))
    assert system_one.evaluate({}, {}).status == "ok"


def test_retry_after_longer_than_budget_does_not_hammer_endpoint(jev):
    calls = []
    install(lambda request: calls.append(1) or httpx.Response(429, headers={"Retry-After": "2"}))
    assert system_one.evaluate({}, {}).status == "rate_limited"
    assert calls == [1]


def test_repeated_429_is_rate_limited_and_5xx_is_error(jev):
    install(lambda request: httpx.Response(429))
    assert system_one.evaluate({}, {}).status == "rate_limited"
    install(lambda request: httpx.Response(503))
    assert system_one.evaluate({}, {}).status == "error"


def test_401_is_auth_failed(jev):
    install(lambda request: httpx.Response(401))
    assert system_one.evaluate({}, {}).status == "auth_failed"
    assert system_one.status()["last_status"] == "auth_failed"


def test_timeout_falls_back(jev):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    install(slow)
    started = time.perf_counter()
    assert system_one.evaluate({}, {}).status == "timeout"
    assert time.perf_counter() - started < 1.0


def test_bad_json_is_error(jev):
    install(lambda request: httpx.Response(200, content=b"not json"))
    assert system_one.evaluate({}, {}).status == "error"


def test_status_never_contains_key(jev):
    install(lambda request: httpx.Response(200, json={"answers": {}}))
    system_one.evaluate({}, {})
    assert "test-key-123" not in repr(system_one.status())


def test_hanging_server_hits_hard_budget(jev):
    def hang(request):
        time.sleep(2)
        return httpx.Response(200, json={"answers": {}})

    install(hang)
    started = time.perf_counter()
    assert system_one.evaluate({}, {}).status == "timeout"
    assert time.perf_counter() - started < 1.0


def test_malformed_bodies_are_errors_not_crashes(jev):
    install(lambda request: httpx.Response(200, json=[1, 2]))
    assert system_one.evaluate({}, {}).status == "error"
    install(lambda request: httpx.Response(200, json={"answers": [1]}))
    assert system_one.evaluate({}, {}).status == "error"
    install(lambda request: httpx.Response(200, json={"answers": {}, "usage": {"input_tokens": "n/a"}}))
    result = system_one.evaluate({}, {})
    assert result.status == "ok" and result.input_tokens == 0
