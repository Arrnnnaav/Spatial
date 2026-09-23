import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main, research, system_one, trace  # noqa: E402

BASE = {
    "question": "what does this do?",
    "canvas": {"width": 1280, "height": 720},
    "page": {"url": "https://example.org", "title": "App", "surface": "web"},
    "marks": [
        {
            "type": "rectangle",
            "role": "reference",
            "x": 100,
            "y": 100,
            "width": 300,
            "height": 120,
        }
    ],
    "anchors": [
        {
            "id": "big",
            "type": "p",
            "text": "A long paragraph about the export feature",
            "bbox": {"x": 100, "y": 100, "width": 300, "height": 120},
        },
        {
            "id": "btn",
            "type": "button",
            "text": "Export",
            "bbox": {"x": 120, "y": 120, "width": 60, "height": 20},
        },
        {
            "id": "far",
            "type": "p",
            "text": "footer",
            "bbox": {"x": 0, "y": 650, "width": 100, "height": 20},
        },
    ],
    "research": True,
}


@pytest.fixture
def jev(monkeypatch):
    """Fake System One: answers are chosen by element text, whatever letters build_request assigned."""
    sent = {}

    def install(target_text=None, conf=0.9, second=None, **routing):
        def fake(state, questions):
            sent["state"], sent["questions"] = state, questions
            letter = {e["text"]: l for l, e in state["elements"].items()}
            answers = {
                "mode": {"choice": routing.get("mode", "explain")},
                "needs_outside_facts": {"noul": routing.get("facts", 0.1)},
                "visual": {"noul": routing.get("visual", 0.1)},
            }
            if "same_target" in questions:
                answers["same_target"] = {"noul": routing.get("same", 0.9)}
            if "target" in questions and target_text:
                first = letter[target_text]
                probs = {first: 0.9, "none": 0.1}
                if second:
                    probs = {first: 0.5, letter[second]: 0.45, "none": 0.05}
                answers["target"] = {
                    "choice": first,
                    "confidence": conf,
                    "probabilities": probs,
                }
            return system_one.Result("ok", answers, "jev-1.13.0", 470)

        monkeypatch.setattr(main.semantic.system_one, "evaluate", fake)

    gathered = []
    monkeypatch.setattr(
        research, "gather", lambda q, anchors, max_sources=4: gathered.append(q) or []
    )
    return install, sent, gathered


def test_hybrid_target_routing_and_research_gate(jev):
    install, _, gathered = jev
    install(target_text="Export", mode="define", facts=0.1)
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json=BASE).json()
    assert (
        body["anchors_used"][0]["id"] == "btn"
        and body["anchors_used"][0]["is_target"] is True
    )
    assert body["resolution_v3"]["selected_candidate_id"] == "btn"
    assert (
        body["resolution_v3"]["resolver"] == "hybrid-jev-1.13.0"
        and body["resolution_v3"]["semantic_confidence"] == 0.9
    )
    assert body["routing"]["mode"] == "define" and body["clarify"] == []
    assert (
        body["system_one"]["status"] == "ok" and gathered == []
    )  # research skipped: no outside facts needed


def test_research_runs_when_facts_needed(jev):
    install, _, gathered = jev
    install(target_text="Export", facts=0.95)
    with TestClient(main.app) as client:
        client.post("/api/ask", json=BASE)
    assert gathered == ["what does this do?"]


def test_ambiguous_returns_clarify(jev):
    install, _, _ = jev
    install(
        target_text="Export",
        conf=0.2,
        second="A long paragraph about the export feature",
    )
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json=BASE).json()
    assert [c["id"] for c in body["clarify"]] == ["btn", "big"] and body[
        "confirmation_required"
    ] is True
    assert body["resolution_v3"]["abstained"] is True


def test_jev_failure_is_todays_behaviour(jev, monkeypatch):
    _, _, gathered = jev
    monkeypatch.setattr(
        main.semantic.system_one,
        "evaluate",
        lambda s, q: system_one.Result("timeout", latency_ms=1500),
    )
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json=BASE).json()
    assert (
        body["routing"] is None
        and body["clarify"] == []
        and body["system_one"]["status"] == "timeout"
    )
    assert body["resolution_v3"]["resolver"] == "structured-anchor-v1" and gathered == [
        "what does this do?"
    ]
    assert not any(
        a.get("is_target") for a in body["anchors_used"]
    )  # prompt exactly as before


def test_pinned_target_skips_target_question(jev):
    install, sent, _ = jev
    install(target_text="A long paragraph about the export feature")
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json={**BASE, "target_id": "btn"}).json()
    assert "target" not in sent["questions"] and body["anchors_used"][0]["id"] == "btn"


def test_pinned_target_must_exist(jev):
    install, _, _ = jev
    install(target_text="Export")
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json={**BASE, "target_id": "ghost"}).json()
    assert body["anchors_used"][0]["id"] == "btn"


def test_target_promoted_even_if_filtered(jev):
    install, _, _ = jev
    install(target_text="footer")  # score below the anchors_used cut
    # mark bottom at y=655 overlaps 5 of the footer's 20 px: score ~0.24 -> shortlisted (>= 0.10) but below the 0.25 cut
    marks = [
        {
            "type": "rectangle",
            "role": "reference",
            "x": 0,
            "y": 100,
            "width": 400,
            "height": 555,
        }
    ]
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json={**BASE, "marks": marks}).json()
    assert (
        body["anchors_used"][0]["id"] == "far"
        and body["anchors_used"][0]["is_target"] is True
    )


def test_followup_keeps_previous_target(jev):
    install, sent, _ = jev
    install(target_text="Export")
    with TestClient(main.app) as client:
        first = client.post("/api/ask", json=BASE).json()
        install(target_text="A long paragraph about the export feature", same=0.9)
        second = client.post(
            "/api/ask", json={**BASE, "question": "and why?", "context_id": first["id"]}
        ).json()
    assert (
        "same_target" in sent["questions"] and second["anchors_used"][0]["id"] == "btn"
    )


def test_trace_records_judgment_without_key(jev, tmp_path, monkeypatch):
    install, _, _ = jev
    install(target_text="Export")
    monkeypatch.setattr(trace.settings, "trace_dir", str(tmp_path))
    monkeypatch.setattr(system_one.settings, "typesafe_api_key", "secret-key-xyz")
    trace._state["error"] = None
    trace.set_enabled(True)
    with TestClient(main.app) as client:
        client.post("/api/ask", json={**BASE, "target_id": "btn"})
    raw = "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.jsonl"))
    record = json.loads(raw.splitlines()[0])
    assert (
        record["system_one"]["status"] == "ok"
        and record["label"] == "btn"
        and "secret-key-xyz" not in raw
    )


def test_health_reports_system_one():
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["system_one"]["backend"] == "off"


def test_multi_mark_prompt_unchanged_without_system_one(jev, monkeypatch):
    monkeypatch.setattr(main.semantic.system_one, "evaluate", lambda s, q: system_one.Result("off"))
    marks = [{"type": "rectangle", "role": "source", "x": 110, "y": 110, "width": 80, "height": 40},
             {"type": "rectangle", "role": "target", "x": 0, "y": 645, "width": 110, "height": 30}]
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json={**BASE, "marks": marks}).json()
    assert not any(a.get("is_target") for a in body["anchors_used"])
    assert {a["role"] for a in body["anchors_used"]} == {"source", "target"}
