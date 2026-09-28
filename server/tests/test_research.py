import os
import sys
from pathlib import Path

os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
os.environ["SPATIAL_PROVIDERS"] = "nothing"  # deterministic fallback, no network
os.environ["SPATIAL_OCR"] = "0"
os.environ["SPATIAL_API_TOKEN"] = ""

sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient

from app import research
from app.main import app

PAGE = """
Gradient descent overview. Random intro sentence about nothing.
The update rule subtracts the gradient because the gradient points toward higher loss; moving against it lowers the loss.
The learning rate controls the size of each step and is often decayed over time.
Footer links and cookie notice. Privacy policy.
"""


def test_select_passages_prefers_overlap_and_caps_count():
    passages = research.select_passages(PAGE, "why subtract the gradient?", n=2)
    assert passages and "subtracts the gradient" in passages[0]
    assert len(passages) <= 2
    assert research.select_passages("", "anything") == []


def test_build_query_grounds_in_anchor_text():
    query = research.build_query(
        "Why the minus sign?",
        [{"text": "theta = theta - eta grad L of theta extra words here beyond eight"}],
    )
    assert (
        query.startswith("Why the minus sign?")
        and "theta" in query
        and "beyond" not in query
    )


def test_sources_block_and_cited_ids():
    sources = [
        {"id": 1, "url": "https://a.example", "title": "A", "passages": ["p1"]},
        {"id": 2, "url": "https://b.example", "title": "B", "passages": ["p2"]},
    ]
    block = research.sources_block(sources)
    assert "[1] A" in block and "[2] B" in block and "    p2" in block
    assert research.cited_ids("Claim [2]. Other [9] and [1].", sources) == [1, 2]


def test_ask_with_research_returns_sources(monkeypatch):
    fake = [
        {
            "id": 1,
            "url": "https://x.example/gd",
            "title": "GD",
            "passages": ["the gradient points uphill so we subtract it"],
        }
    ]
    monkeypatch.setattr(
        research, "gather", lambda question, anchors, max_sources=4, mode=None, use_system_one=True: fake
    )
    with TestClient(app) as client:
        body = client.post(
            "/api/ask",
            json={
                "question": "why minus?",
                "research": True,
                "marks": [
                    {
                        "type": "rectangle",
                        "role": "reference",
                        "x": 10,
                        "y": 10,
                        "width": 50,
                        "height": 20,
                    }
                ],
                "canvas": {"width": 800, "height": 600},
                "anchors": [
                    {
                        "id": "a1",
                        "type": "p",
                        "text": "theta = theta - eta grad",
                        "bbox": {"x": 5, "y": 5, "width": 60, "height": 30},
                    }
                ],
            },
        ).json()
    assert body["sources"] == fake
    assert (
        "GD" in body["answer"]
    )  # deterministic fallback lists the sources when no provider is configured
