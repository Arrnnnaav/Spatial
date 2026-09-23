import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import semantic, system_one  # noqa: E402
from app.contracts import from_v2, resolver_inputs  # noqa: E402
from app.resolver import resolve_marks  # noqa: E402

CANVAS = {"width": 1280, "height": 720}


def ctx_for(marks, anchors, question="what is this?", surface="web"):
    ctx = from_v2(
        question=question,
        marks=marks,
        anchors=anchors,
        canvas=CANVAS,
        page={"surface": surface},
        privacy_policy="anchors_only",
    )
    _, _, resolver_anchors = resolver_inputs(ctx)
    return ctx, resolve_marks(*resolver_inputs(ctx)), resolver_anchors


TOOLBAR = [
    {
        "id": "bar",
        "type": "div",
        "text": "File Edit View",
        "bbox": {"x": 0, "y": 0, "width": 1280, "height": 48},
    },
    {
        "id": "edit",
        "type": "button",
        "text": "Edit",
        "bbox": {"x": 110, "y": 8, "width": 80, "height": 32},
    },
]


def test_point_wording_and_containment():
    ctx, res, anchors = ctx_for([{"type": "point", "x": 150, "y": 24}], TOOLBAR)
    state, questions, letters = semantic.build_request(ctx, res, anchors)
    by_id = {cid: state["elements"][letter] for letter, cid in letters.items()}
    assert by_id["edit"]["position"] == "the clicked spot is on this element"
    assert by_id["bar"]["contains_elements"] and by_id["edit"]["inside_elements"]
    assert state["mark"] == "a single click on one spot"
    assert set(questions) == {"target", "mode", "needs_outside_facts", "visual"}
    assert "none" in questions["target"]["criteria"]


def test_open_stroke_wording():
    lines = [
        {
            "id": f"l{i}",
            "type": "pdf-text",
            "text": f"line {i}",
            "page": 1,
            "bbox": {"x": 140, "y": 150 + i * 34, "width": 620, "height": 24},
        }
        for i in range(4)
    ]
    stroke = {
        "type": "polygon",
        "closed": False,
        "points": [[140, 216], [760, 217]],
        "x": 140,
        "y": 176,
        "width": 620,
        "height": 81,
    }
    ctx, res, anchors = ctx_for([stroke], lines, surface="pdf")
    state, _, letters = semantic.build_request(ctx, res, anchors)
    by_id = {
        cid: state["elements"][letter]["position"] for letter, cid in letters.items()
    }
    assert (
        by_id["l1"]
        == "the stroke is drawn directly under this element, like an underline"
    )
    assert by_id["l2"] == "this element is below the stroke"


def test_area_wording_and_followup_question():
    anchors = [
        {
            "id": "p",
            "type": "p",
            "text": "para",
            "bbox": {"x": 100, "y": 100, "width": 200, "height": 50},
        }
    ]
    ctx, res, ra = ctx_for(
        [{"type": "rectangle", "x": 90, "y": 90, "width": 220, "height": 70}], anchors
    )
    state, questions, _ = semantic.build_request(
        ctx, res, ra, previous_question="what is it?"
    )
    assert state["elements"]["A"]["position"] == "entirely inside the marked area"
    assert state["previous_question_in_this_conversation"] == "what is it?"
    assert "same_target" in questions


def test_no_shortlist_and_pinned_skip_target_question():
    ctx, res, ra = ctx_for(
        [{"type": "rectangle", "x": 900, "y": 600, "width": 20, "height": 20}], TOOLBAR
    )
    _, questions, letters = semantic.build_request(ctx, res, ra)
    assert "target" not in questions and letters == {}
    ctx, res, ra = ctx_for([{"type": "point", "x": 150, "y": 24}], TOOLBAR)
    _, questions, _ = semantic.build_request(ctx, res, ra, pinned=True)
    assert "target" not in questions


def answers(choice="A", conf=0.9, probs=None, **extra):
    base = {
        "target": {
            "choice": choice,
            "confidence": conf,
            "probabilities": probs or {"A": 0.9, "B": 0.1, "none": 0.0},
        },
        "mode": {"choice": "define"},
        "needs_outside_facts": {"noul": 0.1},
        "visual": {"noul": 0.7},
    }
    base.update(extra)
    return base


def test_decide_hybrid_and_routing():
    j = semantic.decide(answers(), {"A": "a", "B": "b"}, "b")
    assert j.target_id == "a" and j.semantic_confidence == 0.9 and not j.ambiguous
    assert j.mode == "define" and j.needs_outside_facts == 0.1 and j.visual == 0.7


def test_target_gate_uses_pick_probability_not_confidence():
    # Confidence is diluted by the extra options; Jev still prefers A more likely than not -> take A.
    likely = semantic.decide(answers(conf=0.43, probs={"A": 0.62, "B": 0.37, "none": 0.01}), {"A": "a", "B": "b"}, "b")
    assert likely.target_id == "a"
    unsure = semantic.decide(answers(conf=0.1, probs={"A": 0.4, "B": 0.35, "none": 0.25}), {"A": "a", "B": "b"}, "b")
    assert unsure.target_id == "b"


def test_decide_ambiguity_rules():
    close = semantic.decide(
        answers(conf=0.2, probs={"A": 0.5, "B": 0.45, "none": 0.05}),
        {"A": "a", "B": "b"},
        "a",
    )
    assert close.ambiguous and close.clarify_ids == ["a", "b"]
    none = semantic.decide(
        answers(choice="none", conf=0.4, probs={"A": 0.3, "B": 0.1, "none": 0.6}),
        {"A": "a", "B": "b"},
        "a",
    )
    assert none.ambiguous and none.target_id == "a"


def test_decide_unknown_letter_is_none():
    j = semantic.decide(
        answers(choice="F", conf=0.99, probs={"F": 0.99, "A": 0.01}), {"A": "a"}, "a"
    )
    assert j.target_id == "a" and j.ambiguous


def test_decide_missing_fields_are_absent():
    j = semantic.decide({"mode": {"choice": "nonsense"}}, {}, None)
    assert (
        j.mode is None
        and j.needs_outside_facts is None
        and not j.ambiguous
        and not j.asked_target
    )


def test_final_target_priority():
    j = semantic.decide(answers(same_target={"noul": 0.9}), {"A": "a", "B": "b"}, "b")
    known = {"a", "b", "c"}
    assert semantic.final_target(j, "b", "c", "b", known) == "c"  # pinned wins
    assert (
        semantic.final_target(j, "b", None, "b", known) == "b"
    )  # same target as last turn
    assert (
        semantic.final_target(j, "b", None, "gone", known) == "a"
    )  # previous target no longer present
    off = semantic.Judgment(status="timeout")
    assert semantic.final_target(off, "b", None, None, known) == "b"


def test_judge_uses_transport_and_maps_failures(monkeypatch):
    ctx, res, ra = ctx_for([{"type": "point", "x": 150, "y": 24}], TOOLBAR)
    sent = {}

    def fake(state, questions):
        sent["questions"] = questions
        letter = next(l for l, e in state["elements"].items() if e["text"] == "Edit")
        return system_one.Result(
            "ok",
            answers(choice=letter, probs={letter: 0.95, "none": 0.05}),
            "jev-1.13.0",
            480,
        )

    monkeypatch.setattr(semantic.system_one, "evaluate", fake)
    j = semantic.judge(ctx, res, ra)
    assert (
        j.status == "ok"
        and j.target_id == "edit"
        and j.model == "jev-1.13.0"
        and j.latency_ms == 480
    )
    monkeypatch.setattr(
        semantic.system_one,
        "evaluate",
        lambda s, q: system_one.Result("timeout", latency_ms=1500),
    )
    j = semantic.judge(ctx, res, ra)
    assert j.status == "timeout" and j.target_id is None


def test_request_key_is_stable():
    assert semantic.request_key({"b": 1, "a": 2}, {"q": 1}) == semantic.request_key(
        {"a": 2, "b": 1}, {"q": 1}
    )


def test_decide_tolerates_garbage_answers():
    j = semantic.decide({"target": "A", "visual": "yes", "mode": 5, "needs_outside_facts": {"noul": "high"}}, {"A": "a"}, "a")
    assert j.target_id == "a" and j.visual is None and j.mode is None and j.needs_outside_facts is None
    j = semantic.decide({"target": {"choice": "A", "confidence": "x", "probabilities": {"A": "x", "B": 0.2}}}, {"A": "a", "B": "b"}, "b")
    assert j.target_id == "b"


def test_judge_never_raises(monkeypatch):
    ctx, res, ra = ctx_for([{"type": "point", "x": 150, "y": 24}], TOOLBAR)

    def boom(state, questions):
        raise RuntimeError("schema changed")

    monkeypatch.setattr(semantic.system_one, "evaluate", boom)
    assert semantic.judge(ctx, res, ra).status == "error"


def test_request_never_carries_binary():
    import json as _json
    blob = "data:image/png;base64," + "iVBORw0KGgo" * 2000
    anchors = [{"id": "img", "type": blob, "text": "QUJD" * 200, "bbox": {"x": 100, "y": 100, "width": 50, "height": 50}}]
    ctx, res, ra = ctx_for([{"type": "rectangle", "x": 90, "y": 90, "width": 80, "height": 80}], anchors)
    state, questions, _ = semantic.build_request(ctx, res, ra)
    raw = _json.dumps([state, questions])
    assert "data:image" not in raw and "QUJDQUJD" * 10 not in raw
    assert len(state["elements"]["A"]["kind"]) <= 40


SOURCES = [
    {"url": "https://a.example", "title": "A", "passages": ["The gradient points uphill.", "Cookie banner text."], "credibility": 0.85},
    {"url": "https://b.example", "title": "B", "passages": ["Subtract the gradient to lower the loss."], "credibility": 0.6},
]


def test_rank_passages_keeps_relevant_and_orders_sources(monkeypatch):
    sent = {}

    def fake(state, questions):
        sent["state"], sent["questions"] = state, questions
        # P1 = A/uphill (2.0), P2 = A/cookie (0.2), P3 = B/subtract (2.9)
        scores = {"P1": 2.0, "P2": 0.2, "P3": 2.9}
        return system_one.Result("ok", {k: {"type": "score", "score": v} for k, v in scores.items()})

    monkeypatch.setattr(semantic.system_one, "evaluate", fake)
    ranked = semantic.rank_passages("why subtract?", "theta - eta grad", SOURCES)
    assert [s["title"] for s in ranked] == ["B", "A"]
    assert ranked[1]["passages"] == ["The gradient points uphill."]
    assert set(sent["questions"]) == {"P1", "P2", "P3"} and sent["questions"]["P1"]["type"] == "score"
    assert len(sent["questions"]["P1"]["criteria"]) == 4


def test_rank_passages_none_when_unavailable_or_empty(monkeypatch):
    monkeypatch.setattr(semantic.system_one, "evaluate", lambda s, q: system_one.Result("timeout"))
    assert semantic.rank_passages("q", "m", SOURCES) is None
    assert semantic.rank_passages("q", "m", []) is None


def test_rank_passages_drops_everything_irrelevant_but_never_crashes(monkeypatch):
    monkeypatch.setattr(semantic.system_one, "evaluate",
                        lambda s, q: system_one.Result("ok", {k: {"score": "bad"} for k in q}))
    assert semantic.rank_passages("q", "m", SOURCES) is None  # unusable answers -> keep search order


def test_check_citations_flags_unsupported(monkeypatch):
    sources = [dict(s, id=i + 1) for i, s in enumerate(SOURCES)]
    answer = "You subtract the gradient because it points uphill [1]. This lowers the loss [2]. No citation here."
    sent = {}

    def fake(state, questions):
        sent["questions"] = questions
        verdicts = {"C1": ("supports", 0.9), "C2": ("unrelated", 0.7)}
        return system_one.Result("ok", {k: {"choice": v[0], "probabilities": {v[0]: v[1]}} for k, v in verdicts.items()})

    monkeypatch.setattr(semantic.system_one, "evaluate", fake)
    checks, unsupported = semantic.check_citations(answer, sources)
    assert len(sent["questions"]) == 2 and sent["questions"]["C1"]["type"] == "choice"
    assert [(c["sentence_index"], c["source_id"], c["verdict"]) for c in checks] == [(0, 1, "supports"), (1, 2, "unrelated")]
    assert unsupported == [2]


def test_check_citations_skips_without_citations_or_jev(monkeypatch):
    assert semantic.check_citations("No refs at all.", [dict(SOURCES[0], id=1)]) == ([], [])
    monkeypatch.setattr(semantic.system_one, "evaluate", lambda s, q: system_one.Result("error"))
    assert semantic.check_citations("Claim [1].", [dict(SOURCES[0], id=1)]) == ([], [])
