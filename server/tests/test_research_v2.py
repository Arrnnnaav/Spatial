import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import research  # noqa: E402

TAVILY_BODY = {
    "results": [
        {
            "url": "https://en.wikipedia.org/wiki/Gradient_descent",
            "title": "Gradient descent - Wikipedia",
            "content": "The gradient points uphill. [...] Moving against it lowers the loss.",
            "score": 0.91,
        },
        {
            "url": "https://blog.example.com/gd",
            "title": "GD blog",
            "content": "Subtract the gradient.",
            "score": 0.62,
        },
        {
            "url": "https://en.wikipedia.org/wiki/Gradient_descent/",
            "title": "dup",
            "content": "dup",
            "score": 0.5,
        },
    ]
}


@pytest.fixture
def tavily(monkeypatch):
    monkeypatch.setattr(research.settings, "tavily_api_key", "tvly-test-key")
    monkeypatch.setattr(research.settings, "research_search", "auto")
    seen = {}

    def install(handler):
        monkeypatch.setattr(research, "_tavily_transport", httpx.MockTransport(handler))

    return install, seen


def test_tavily_request_shape_and_parsing(tavily):
    install, seen = tavily

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json=TAVILY_BODY)

    install(handler)
    hits = research._tavily_search("why subtract the gradient", 5)
    assert (
        seen["auth"] == "Bearer tvly-test-key"
        and seen["body"]["search_depth"] == "fast"
    )
    assert seen["body"]["chunks_per_source"] == 3 and seen["body"]["max_results"] == 5
    assert hits[0]["passages"] == [
        "The gradient points uphill.",
        "Moving against it lowers the loss.",
    ]
    assert hits[0]["score"] == 0.91


def test_tavily_failure_returns_empty(tavily):
    install, _ = tavily
    install(lambda request: httpx.Response(432, json={"detail": "limit"}))
    assert research._tavily_search("q", 5) == []


def test_dedupe_and_credibility():
    hits = [
        {"url": u, "title": t, "passages": ["p"], "score": s}
        for u, t, s in (
            ("https://en.wikipedia.org/wiki/X", "W", 0.5),
            ("https://en.wikipedia.org/wiki/X/", "dup", 0.9),
            ("https://www.nist.gov/a", "NIST", 0.4),
            ("https://random.example.com/b", "R", 0.8),
        )
    ]
    out = research.dedupe_and_score(hits)
    assert [s["title"] for s in out] == ["W", "NIST", "R"]
    assert {s["title"]: s["credibility"] for s in out} == {
        "W": 0.85,
        "NIST": 0.95,
        "R": 0.6,
    }


def test_compare_builds_one_query_per_role():
    anchors = [
        {"text": "Adam optimizer adapts learning rates", "role": "source"},
        {"text": "SGD with momentum", "role": "target"},
    ]
    queries = research.build_queries("how do these differ?", anchors, mode="compare")
    assert len(queries) == 2 and "Adam" in queries[0] and "SGD" in queries[1]
    assert len(research.build_queries("why?", anchors, mode="explain")) == 1
    assert len(research.build_queries("compare", anchors[:1], mode="compare")) == 1


def test_gather_uses_tavily_and_numbers_sources(tavily, monkeypatch):
    install, _ = tavily
    install(lambda request: httpx.Response(200, json=TAVILY_BODY))
    monkeypatch.setattr(
        research,
        "_ddg_search",
        lambda q, k: pytest.fail("DDG must not run when Tavily answers"),
    )
    monkeypatch.setattr(
        research, "rank_passages", lambda question, marked, sources: None
    )
    sources = research.gather("why subtract?", [{"text": "theta - eta grad"}])
    assert [s["id"] for s in sources] == [1, 2] and sources[0]["url"].startswith(
        "https://en.wikipedia.org"
    )
    assert sources[0]["passages"] and "credibility" in sources[0]


def test_gather_falls_back_to_ddg_without_key(monkeypatch):
    monkeypatch.setattr(research.settings, "tavily_api_key", None)
    monkeypatch.setattr(
        research,
        "_ddg_search",
        lambda q, k: [
            {"url": "https://a.example/x", "title": "A", "snippet": "snippet text"}
        ],
    )
    monkeypatch.setattr(research, "fetch_text", lambda url: "")
    monkeypatch.setattr(
        research, "rank_passages", lambda question, marked, sources: None
    )
    sources = research.gather("q", [{"text": "t"}])
    assert sources[0]["passages"] == ["snippet text"]


def test_gather_applies_jev_ranking_when_available(tavily, monkeypatch):
    install, _ = tavily
    install(lambda request: httpx.Response(200, json=TAVILY_BODY))
    monkeypatch.setattr(
        research,
        "rank_passages",
        lambda question, marked, sources: [
            dict(sources[1], passages=["Subtract the gradient."])
        ],
    )
    sources = research.gather("why subtract?", [{"text": "t"}])
    assert [s["title"] for s in sources] == ["GD blog"] and sources[0]["id"] == 1


def test_gemini_is_gone():
    assert not hasattr(research, "_gemini_search")
