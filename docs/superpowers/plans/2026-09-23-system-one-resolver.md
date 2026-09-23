# System-One Resolver (Jev) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One Jev request per ask picks the target (hybrid with geometry), flags ambiguity, and routes the answer (mode, research, vision, follow-up), with a silent fallback to today's behaviour on any Jev failure.

**Architecture:** `system_one.py` is a thin kept-alive HTTP transport to `/v1/systemone`. `semantic.py` turns a `SpatialContext` + deterministic resolution into Jev state/questions (geometry in words), and turns answers into a `Judgment` and final decisions. `main.py` calls `semantic.judge()` between resolution and research; `providers.py` gains a mode line, a vision switch and a target-first prompt. The eval harness replays a recorded cassette so tests never hit the network.

**Tech Stack:** Python 3.12, FastAPI, httpx (MockTransport in tests), pydantic 2, pytest; vanilla JS MV3 extension.

**Spec:** `docs/superpowers/specs/2026-09-23-system-one-resolver-design.md` (evidence: `docs/TYPESAFE_OPPORTUNITIES.md` → Results)

## Global Constraints

- Thresholds: `TARGET_MIN_CONF = 0.5`, `AMBIGUITY_RATIO = 0.4`, `FACTS_MIN = 0.8`, `VISUAL_MIN = 0.5`, `SAME_TARGET_MIN = 0.5`; shortlist max 8 (letters A–H).
- Settings: `SPATIAL_SYSTEM_ONE=jev|off` (default `jev` when `TYPESAFE_API_KEY` is set, else `off`), `TYPESAFE_API_KEY`, `TYPESAFE_MODEL=jev-latest`, `TYPESAFE_BASE_URL=https://api.typesafe.ai`, `SPATIAL_SYSTEM_ONE_TIMEOUT=1.5`.
- Jev never writes the answer; geometry reaches Jev only as words; no pixels ever sent to Jev.
- Any Jev failure → exactly today's behaviour (research as requested, vision as before, geometry target).
- Tests never call the network: `server/tests/conftest.py` forces `SPATIAL_SYSTEM_ONE=off`; transport tests use `httpx.MockTransport`; eval hybrid uses the cassette.
- Keys are never printed, logged, returned by an endpoint, or written to traces.
- Golden parity (`geometry.js` ↔ `resolver.py`) must stay green; resolver math is untouched.

## Review Focus

1. **A Jev answer for a letter that is not in the shortlist** (model drift, stale cassette) must be treated as `none`, never crash → `test_decide_unknown_letter_is_none` (Task 2).
2. **Pinned `target_id` that is not among the request's candidates** (stale chip after a page change) must be ignored, not trusted → `test_pinned_target_must_exist` (Task 4).
3. **Timeout budget**: a slow Jev (hangs) must return within ~`SPATIAL_SYSTEM_ONE_TIMEOUT` and fall back → `test_timeout_falls_back` (Task 1).
4. **Key leakage**: `/api/health` and traces must not contain the key → `test_status_never_contains_key` (Task 1) and trace assertion in Task 4.
5. **Jev picks a low-ranked candidate** (below the 0.25 `anchors_used` cut) — the target must still reach the prompt and the highlight → `test_target_promoted_even_if_filtered` (Task 4).

## File Structure

| File | Responsibility |
|---|---|
| `server/app/system_one.py` (new) | Kept-alive transport, timeout budget, retry, statuses, warm-up, health status |
| `server/app/semantic.py` (new) | Wording, request building, `decide`, `final_target`, `judge`, cassette key |
| `server/app/config.py` | System-One settings |
| `server/app/providers.py` | `MODE_HINTS`, `mode`/`prefer_vision` kwargs, target-first prompt |
| `server/app/main.py` | Lifespan warm-up, `target_id`, judge call, research/vision gates, response fields, trace fields |
| `server/app/trace.py` | `system_one` + `label` in records |
| `server/app/evaluation.py`, `scripts/eval.py` | `--resolver hybrid`, cassette, `--record` |
| `server/tests/conftest.py` (new) | Test env: System One off, no key |
| `extension/content.js`, `extension/popup.html` | "Did you mean" chips + outlines; research label |

---

### Task 1: Settings + System-One transport

**Files:**
- Create: `server/app/system_one.py`, `server/tests/conftest.py`, `server/tests/test_system_one.py`
- Modify: `server/app/config.py`, `server/.env.example`

**Interfaces:**
- Produces: `system_one.Result(status: str, answers: dict, model: str | None = None, latency_ms: int = 0, input_tokens: int = 0)`; `system_one.enabled() -> bool`; `system_one.evaluate(state, questions) -> Result`; `system_one.warm() -> None`; `system_one.status() -> dict`; `system_one.reset(transport=None) -> None`. Statuses: `ok | off | timeout | error | rate_limited | auth_failed`.

- [ ] **Step 1: conftest + failing tests**

`server/tests/conftest.py`:

```python
"""Test environment: never reach the real System One API, whatever server/.env contains."""
import os

os.environ["SPATIAL_SYSTEM_ONE"] = "off"
os.environ["TYPESAFE_API_KEY"] = ""
```

`server/tests/test_system_one.py`:

```python
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import system_one  # noqa: E402

ANSWERS = {"target": {"type": "choice", "choice": "A", "confidence": 0.9, "probabilities": {"A": 0.95, "none": 0.05}}}


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
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": ANSWERS, "usage": {"input_tokens": 321}})

    install(handler)
    result = system_one.evaluate({"q": 1}, {"target": {"type": "choice"}})
    assert result.status == "ok" and result.answers == ANSWERS and result.model == "jev-1.13.0"
    assert result.input_tokens == 321 and seen["auth"] == "Bearer test-key-123" and seen["path"] == "/v1/systemone"
    assert b'"model": "jev-latest"' in seen["body"] or b'"model":"jev-latest"' in seen["body"]


def test_429_retried_once_then_ok(jev):
    replies = [httpx.Response(429), httpx.Response(200, json={"answers": ANSWERS})]
    install(lambda request: replies.pop(0))
    assert system_one.evaluate({}, {}).status == "ok"


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
```

- [ ] **Step 2: Run to verify failure**

Run (from `server/`): `python -m pytest tests/test_system_one.py -q`
Expected: FAIL — `ImportError: cannot import name 'system_one'`.

- [ ] **Step 3: Settings**

In `server/app/config.py` `Settings`, after the trace settings add:

```python
    # System One judgments (app/system_one.py, app/semantic.py): TypeSafe Jev today, Laya later (same protocol).
    typesafe_api_key: str | None = _env("TYPESAFE_API_KEY")
    typesafe_model: str = _env("TYPESAFE_MODEL", "jev-latest")
    typesafe_base_url: str = _env("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
    # Read raw: _env() maps "off" to None, which would fall through to the key-based default.
    system_one_backend: str = (os.environ.get("SPATIAL_SYSTEM_ONE", "").strip().lower()
                               or ("jev" if _env("TYPESAFE_API_KEY") else "off"))
    system_one_timeout: float = float(_env("SPATIAL_SYSTEM_ONE_TIMEOUT", "1.5"))
```

Append to `server/.env.example` (replace the existing System One block's first line comment context, keep keys):

```
SPATIAL_SYSTEM_ONE=                      # jev | off (default: jev when TYPESAFE_API_KEY is set)
SPATIAL_SYSTEM_ONE_TIMEOUT=1.5           # seconds; on timeout the ask falls back to geometry only
TYPESAFE_BASE_URL=https://api.typesafe.ai
```

- [ ] **Step 4: `server/app/system_one.py`**

```python
"""Transport to a System One endpoint (TypeSafe Jev today; Laya later via base URL + model).
One kept-alive client (TLS setup from India costs ~1 s; a warm call ~0.5 s), a hard time budget, one retry on
429/5xx inside that budget. Knows nothing about Spatial; never logs or returns the key."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("spatial.system_one")
_lock = threading.Lock()
_client: httpx.Client | None = None
_transport: httpx.BaseTransport | None = None
_last = {"status": "unknown"}


@dataclass
class Result:
    status: str  # ok | off | timeout | error | rate_limited | auth_failed
    answers: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    latency_ms: int = 0
    input_tokens: int = 0


def enabled() -> bool:
    return settings.system_one_backend == "jev" and bool(settings.typesafe_api_key)


def _client_get() -> httpx.Client:
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(base_url=settings.typesafe_base_url, transport=_transport,
                                   headers={"Authorization": f"Bearer {settings.typesafe_api_key}"},
                                   timeout=settings.system_one_timeout)
        return _client


def reset(transport: httpx.BaseTransport | None = None) -> None:
    """Drop the client (tests, key change). A transport given here is used by the next client."""
    global _client, _transport
    with _lock:
        if _client is not None:
            _client.close()
        _client, _transport = None, transport


def _done(result: Result) -> Result:
    _last["status"] = result.status
    return result


def evaluate(state: Any, questions: dict[str, Any]) -> Result:
    if not enabled():
        return _done(Result("off"))
    body = {"model": settings.typesafe_model, "state": state, "questions": questions}
    started = time.perf_counter()
    deadline = started + settings.system_one_timeout

    def elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    for attempt in (1, 2):
        remaining = deadline - time.perf_counter()
        if remaining <= 0.05:
            return _done(Result("timeout", latency_ms=elapsed()))
        try:
            response = _client_get().post("/v1/systemone", json=body, timeout=remaining)
        except httpx.TimeoutException:
            return _done(Result("timeout", latency_ms=elapsed()))
        except httpx.HTTPError as exc:
            logger.warning("system one request failed: %s", type(exc).__name__)
            return _done(Result("error", latency_ms=elapsed()))
        code = response.status_code
        if code in (401, 403):
            return _done(Result("auth_failed", latency_ms=elapsed()))
        if code == 429 or code >= 500:
            if attempt == 1:
                continue
            return _done(Result("rate_limited" if code == 429 else "error", latency_ms=elapsed()))
        if code >= 400:
            return _done(Result("error", latency_ms=elapsed()))
        try:
            data = response.json()
        except ValueError:
            return _done(Result("error", latency_ms=elapsed()))
        return _done(Result("ok", data.get("answers") or {}, data.get("model"), elapsed(),
                            int((data.get("usage") or {}).get("input_tokens", 0))))
    return _done(Result("error", latency_ms=elapsed()))


def warm() -> None:
    """Open the TLS connection before the first ask. Failures only log."""
    if not enabled():
        return
    try:
        _client_get().get("/", timeout=settings.system_one_timeout)
    except httpx.HTTPError as exc:
        logger.info("system one warm-up failed: %s", type(exc).__name__)


def status() -> dict[str, Any]:
    return {"backend": settings.system_one_backend if enabled() else "off",
            "model": settings.typesafe_model if enabled() else None, "last_status": _last["status"]}
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_system_one.py -q` → 8 passed. Then `python -m pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add server/app/system_one.py server/app/config.py server/.env.example server/tests/conftest.py server/tests/test_system_one.py
git commit -m "feat(server): System One transport (kept-alive, time budget, retry, statuses)"
```

---

### Task 2: `semantic.py` — wording, request, decisions

**Files:**
- Create: `server/app/semantic.py`, `server/tests/test_semantic.py`

**Interfaces:**
- Consumes: `system_one.evaluate`, `system_one.Result`; `contracts.SpatialContext`, `contracts.mark_to_v2`.
- Produces:
  - constants `TARGET_MIN_CONF, AMBIGUITY_RATIO, FACTS_MIN, VISUAL_MIN, SAME_TARGET_MIN, MAX_SHORTLIST, MODES`
  - `Judgment` dataclass: `status, target_id, semantic_confidence, probabilities (dict cid→p), ambiguous, clarify_ids, mode, needs_outside_facts, visual, same_target, model, latency_ms, asked_target (bool)`
  - `deterministic_top(resolution) -> str | None`
  - `build_request(ctx, resolution, anchors, previous_question=None, pinned=False) -> tuple[dict, dict, dict[str, str]]` (state, questions, letter→candidate_id)
  - `decide(answers, letters, deterministic_top) -> Judgment`
  - `final_target(judgment, deterministic_top, pinned, previous_target, known_ids) -> str | None`
  - `judge(ctx, resolution, anchors, previous_question=None, pinned=None) -> Judgment`
  - `request_key(state, questions) -> str`

- [ ] **Step 1: Failing tests** — `server/tests/test_semantic.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import semantic, system_one  # noqa: E402
from app.contracts import from_v2, resolver_inputs  # noqa: E402
from app.resolver import resolve_marks  # noqa: E402

CANVAS = {"width": 1280, "height": 720}


def ctx_for(marks, anchors, question="what is this?", surface="web"):
    ctx = from_v2(question=question, marks=marks, anchors=anchors, canvas=CANVAS, page={"surface": surface},
                  privacy_policy="anchors_only")
    _, _, resolver_anchors = resolver_inputs(ctx)
    return ctx, resolve_marks(*resolver_inputs(ctx)), resolver_anchors


TOOLBAR = [{"id": "bar", "type": "div", "text": "File Edit View", "bbox": {"x": 0, "y": 0, "width": 1280, "height": 48}},
           {"id": "edit", "type": "button", "text": "Edit", "bbox": {"x": 110, "y": 8, "width": 80, "height": 32}}]


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
    lines = [{"id": f"l{i}", "type": "pdf-text", "text": f"line {i}", "page": 1,
              "bbox": {"x": 140, "y": 150 + i * 34, "width": 620, "height": 24}} for i in range(4)]
    stroke = {"type": "polygon", "closed": False, "points": [[140, 216], [760, 217]],
              "x": 140, "y": 176, "width": 620, "height": 81}
    ctx, res, anchors = ctx_for([stroke], lines, surface="pdf")
    state, _, letters = semantic.build_request(ctx, res, anchors)
    by_id = {cid: state["elements"][letter]["position"] for letter, cid in letters.items()}
    assert by_id["l1"] == "the stroke is drawn directly under this element, like an underline"
    assert by_id["l2"] == "this element is below the stroke"


def test_area_wording_and_followup_question():
    anchors = [{"id": "p", "type": "p", "text": "para", "bbox": {"x": 100, "y": 100, "width": 200, "height": 50}}]
    ctx, res, ra = ctx_for([{"type": "rectangle", "x": 90, "y": 90, "width": 220, "height": 70}], anchors)
    state, questions, _ = semantic.build_request(ctx, res, ra, previous_question="what is it?")
    assert state["elements"]["A"]["position"] == "entirely inside the marked area"
    assert state["previous_question_in_this_conversation"] == "what is it?"
    assert "same_target" in questions


def test_no_shortlist_and_pinned_skip_target_question():
    ctx, res, ra = ctx_for([{"type": "rectangle", "x": 900, "y": 600, "width": 20, "height": 20}], TOOLBAR)
    _, questions, letters = semantic.build_request(ctx, res, ra)
    assert "target" not in questions and letters == {}
    ctx, res, ra = ctx_for([{"type": "point", "x": 150, "y": 24}], TOOLBAR)
    _, questions, _ = semantic.build_request(ctx, res, ra, pinned=True)
    assert "target" not in questions


def answers(choice="A", conf=0.9, probs=None, **extra):
    base = {"target": {"choice": choice, "confidence": conf, "probabilities": probs or {"A": 0.9, "B": 0.1, "none": 0.0}},
            "mode": {"choice": "define"}, "needs_outside_facts": {"noul": 0.1}, "visual": {"noul": 0.7}}
    base.update(extra)
    return base


def test_decide_hybrid_and_routing():
    j = semantic.decide(answers(), {"A": "a", "B": "b"}, "b")
    assert j.target_id == "a" and j.semantic_confidence == 0.9 and not j.ambiguous
    assert j.mode == "define" and j.needs_outside_facts == 0.1 and j.visual == 0.7
    low = semantic.decide(answers(conf=0.3), {"A": "a", "B": "b"}, "b")
    assert low.target_id == "b"


def test_decide_ambiguity_rules():
    close = semantic.decide(answers(conf=0.2, probs={"A": 0.5, "B": 0.45, "none": 0.05}), {"A": "a", "B": "b"}, "a")
    assert close.ambiguous and close.clarify_ids == ["a", "b"]
    none = semantic.decide(answers(choice="none", conf=0.4, probs={"A": 0.3, "B": 0.1, "none": 0.6}), {"A": "a", "B": "b"}, "a")
    assert none.ambiguous and none.target_id == "a"


def test_decide_unknown_letter_is_none():
    j = semantic.decide(answers(choice="F", conf=0.99, probs={"F": 0.99, "A": 0.01}), {"A": "a"}, "a")
    assert j.target_id == "a" and j.ambiguous


def test_decide_missing_fields_are_absent():
    j = semantic.decide({"mode": {"choice": "nonsense"}}, {}, None)
    assert j.mode is None and j.needs_outside_facts is None and not j.ambiguous and not j.asked_target


def test_final_target_priority():
    j = semantic.decide(answers(same_target={"noul": 0.9}), {"A": "a", "B": "b"}, "b")
    known = {"a", "b", "c"}
    assert semantic.final_target(j, "b", "c", "b", known) == "c"          # pinned wins
    assert semantic.final_target(j, "b", None, "b", known) == "b"         # same target as last turn
    assert semantic.final_target(j, "b", None, "gone", known) == "a"      # previous target no longer present
    off = semantic.Judgment(status="timeout")
    assert semantic.final_target(off, "b", None, None, known) == "b"


def test_judge_uses_transport_and_maps_failures(monkeypatch):
    ctx, res, ra = ctx_for([{"type": "point", "x": 150, "y": 24}], TOOLBAR)
    sent = {}

    def fake(state, questions):
        sent["questions"] = questions
        letter = next(l for l, e in state["elements"].items() if e["text"] == "Edit")
        return system_one.Result("ok", answers(choice=letter, probs={letter: 0.95, "none": 0.05}), "jev-1.13.0", 480)

    monkeypatch.setattr(semantic.system_one, "evaluate", fake)
    j = semantic.judge(ctx, res, ra)
    assert j.status == "ok" and j.target_id == "edit" and j.model == "jev-1.13.0" and j.latency_ms == 480
    monkeypatch.setattr(semantic.system_one, "evaluate", lambda s, q: system_one.Result("timeout", latency_ms=1500))
    j = semantic.judge(ctx, res, ra)
    assert j.status == "timeout" and j.target_id is None


def test_request_key_is_stable():
    assert semantic.request_key({"b": 1, "a": 2}, {"q": 1}) == semantic.request_key({"a": 2, "b": 1}, {"q": 1})
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_semantic.py -q` → `ImportError: cannot import name 'semantic'`.

- [ ] **Step 3: `server/app/semantic.py`**

```python
"""Spatial's System One judgments: one Jev request per ask decides which object was meant and how to answer.
Geometry stays in code and reaches Jev as words (numbers cost 7 points of accuracy in the spike). Wording and
thresholds come from docs/TYPESAFE_OPPORTUNITIES.md → Results (hybrid 48/49 on the eval set)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app import system_one
from app.contracts import SpatialContext, mark_to_v2

TARGET_MIN_CONF = 0.5
AMBIGUITY_RATIO = 0.4
FACTS_MIN = 0.8
VISUAL_MIN = 0.5
SAME_TARGET_MIN = 0.5
MAX_SHORTLIST = 8
LETTERS = "ABCDEFGH"
MODES = {
    "explain": "explain how or why the marked thing works or what it shows",
    "define": "give the meaning of a word, term, symbol or acronym",
    "summarize": "shorten a longer marked passage, table or section",
    "compare": "compare two marked things or contrast one with another",
    "translate": "translate the marked text into another language",
    "debug_error": "diagnose an error message, bug or broken layout and how to fix it",
    "other": "anything else (rewrite, facts about the thing, prices, publication details, styling)",
}


@dataclass
class Judgment:
    status: str
    target_id: str | None = None
    semantic_confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    ambiguous: bool = False
    clarify_ids: list[str] = field(default_factory=list)
    mode: str | None = None
    needs_outside_facts: float | None = None
    visual: float | None = None
    same_target: float | None = None
    model: str | None = None
    latency_ms: int = 0
    asked_target: bool = False


# --- wording ------------------------------------------------------------------------------------------------

def _area(b: dict) -> float:
    return max(0.0, b["width"]) * max(0.0, b["height"])


def _inter(a: dict, b: dict) -> float:
    w = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    return w * h if w > 0 and h > 0 else 0.0


def _contains(outer: dict, inner: dict) -> bool:
    return (outer["x"] <= inner["x"] and outer["y"] <= inner["y"]
            and outer["x"] + outer["width"] >= inner["x"] + inner["width"]
            and outer["y"] + outer["height"] >= inner["y"] + inner["height"] and _area(outer) > _area(inner))


def mark_phrase(mark: dict) -> str:
    kind = mark["type"]
    if kind == "point":
        return "a single click on one spot"
    if kind == "polygon":
        return "an open stroke, like an underline" if mark.get("closed") is False else "a freehand loop drawn around something"
    return {"rectangle": "a box dragged around something", "circle": "an ellipse dragged around something"}.get(kind, kind)


def relation(box: dict, mark: dict) -> dict[str, str]:
    if mark["type"] == "point":
        x, y = mark["x"], mark["y"]
        on = box["x"] <= x <= box["x"] + box["width"] and box["y"] <= y <= box["y"] + box["height"]
        return {"position": "the clicked spot is on this element" if on else "the clicked spot is not on this element"}
    points = mark.get("points") or []
    if mark["type"] == "polygon" and mark.get("closed") is False and points:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        line_y, left, right = sum(ys) / len(ys), min(xs), max(xs)
        under = max(0.0, min(right, box["x"] + box["width"]) - max(left, box["x"])) / max(1.0, right - left)
        gap = line_y - (box["y"] + box["height"])
        if under >= 0.5 and 0 <= gap <= 16:
            return {"position": "the stroke is drawn directly under this element, like an underline"}
        if box["y"] > line_y:
            return {"position": "this element is below the stroke"}
        if under < 0.2:
            return {"position": "this element is beside the stroke, not over it"}
        return {"position": "this element is above the stroke but not directly on it"}
    m = {k: mark.get(k, 0) for k in ("x", "y", "width", "height")}
    inter = _inter(box, m)
    of_box = inter / _area(box) if _area(box) else 0.0
    of_mark = inter / _area(m) if _area(m) else 0.0
    if of_box >= 0.95:
        position = "entirely inside the marked area"
    elif of_box >= 0.6:
        position = "mostly inside the marked area"
    elif of_box >= 0.2:
        position = "partly inside the marked area"
    else:
        position = "only slightly overlaps the marked area"
    if of_mark >= 0.9 and of_box < 0.95:
        position += "; it covers the whole marked area"
    ratio = _area(box) / _area(m) if _area(m) else 1.0
    size = ("much larger than the marked area" if ratio > 3 else
            "much smaller than the marked area" if ratio < 0.33 else "about the size of the marked area")
    return {"position": position, "size": size}


# --- request ------------------------------------------------------------------------------------------------

def deterministic_top(resolution: dict) -> str | None:
    first = (resolution.get("candidates") or [{}])[0]
    return first.get("anchor_id")


def build_request(ctx: SpatialContext, resolution: dict, anchors: list[dict], previous_question: str | None = None,
                  pinned: bool = False) -> tuple[dict, dict, dict[str, str]]:
    first = (resolution.get("candidates") or [{}])[0]
    ranked = [item["id"] for item in first.get("anchors_ranked", [])][:MAX_SHORTLIST]
    by_id = {a["id"]: a for a in anchors}
    ranked = [cid for cid in ranked if cid in by_id]
    mark = mark_to_v2(ctx.marks[0])
    letters = dict(zip(LETTERS, ranked))
    elements: dict[str, dict] = {}
    for letter, cid in letters.items():
        box = by_id[cid]["bbox"]
        element = {"kind": by_id[cid].get("type") or "element", "text": (by_id[cid].get("text") or "(no text)")[:300],
                   **relation(box, mark)}
        inside = [l2 for l2, c2 in letters.items() if l2 != letter and _contains(by_id[c2]["bbox"], box)]
        contains = [l2 for l2, c2 in letters.items() if l2 != letter and _contains(box, by_id[c2]["bbox"])]
        if inside:
            element["inside_elements"] = inside
        if contains:
            element["contains_elements"] = contains
        elements[letter] = element
    top = by_id.get(ranked[0]) if ranked else None
    state: dict[str, Any] = {
        "user_question": ctx.question,
        "mark": mark_phrase(mark),
        "screen": {"pdf": "a PDF document", "desktop": "an application window"}.get(ctx.surface.kind, "a web page"),
        "elements": elements,
        "marked": {"kind": (top or {}).get("type") or "image region", "text": ((top or {}).get("text") or "(no text)")[:300]},
    }
    if previous_question:
        state["previous_question_in_this_conversation"] = previous_question[:300]
    questions: dict[str, Any] = {
        "mode": {"type": "choice", "instructions": "What kind of help does the user want for the marked thing?",
                 "criteria": MODES},
        "needs_outside_facts": {"type": "noul", "instructions": "Does answering `user_question` well require facts that "
                                "are not in `marked` and may be current or specific (dates, people, prices, versions, "
                                "whether a claim is still true)?"},
        "visual": {"type": "noul", "instructions": "Is the marked thing mainly visual (a chart, diagram, image, icon or "
                   "UI layout) so that the answer needs to see it rather than read its text?"},
    }
    if letters and not pinned:
        criteria = {letter: f"element {letter}: {el['kind']} “{el['text'][:80]}”" for letter, el in elements.items()}
        criteria["none"] = "none of the listed elements is what the user marked"
        questions["target"] = {"type": "choice", "criteria": criteria,
                               "instructions": "The user marked part of the screen (`mark`) and asked `user_question`. "
                                               "Which one element in `elements` is the user referring to?"}
    if previous_question:
        questions["same_target"] = {"type": "noul", "instructions": "Is `user_question` about the same marked thing as "
                                    "`previous_question_in_this_conversation`, rather than a new thing?"}
    return state, questions, letters


def request_key(state: dict, questions: dict) -> str:
    return hashlib.sha256(json.dumps([state, questions], sort_keys=True, ensure_ascii=True).encode()).hexdigest()


# --- decisions ----------------------------------------------------------------------------------------------

def _noul(answers: dict, key: str) -> float | None:
    value = (answers.get(key) or {}).get("noul")
    return float(value) if isinstance(value, (int, float)) else None


def decide(answers: dict, letters: dict[str, str], deterministic: str | None) -> Judgment:
    judgment = Judgment(status="ok", target_id=deterministic)
    target = answers.get("target") or {}
    if target and letters:
        judgment.asked_target = True
        probs = {letters[letter]: float(p) for letter, p in (target.get("probabilities") or {}).items() if letter in letters}
        judgment.probabilities = probs
        picked = letters.get(target.get("choice"))
        confidence = target.get("confidence")
        judgment.semantic_confidence = float(confidence) if isinstance(confidence, (int, float)) else None
        if picked and (judgment.semantic_confidence or 0.0) >= TARGET_MIN_CONF:
            judgment.target_id = picked
        ordered = sorted(probs.values(), reverse=True)
        close = len(ordered) > 1 and ordered[0] > 0 and ordered[1] / ordered[0] >= AMBIGUITY_RATIO
        judgment.ambiguous = picked is None or close
        if judgment.ambiguous:
            ranked = sorted(probs, key=probs.get, reverse=True)
            judgment.clarify_ids = ranked[:4] if len(ranked) >= 2 else []
    mode = (answers.get("mode") or {}).get("choice")
    judgment.mode = mode if mode in MODES else None
    judgment.needs_outside_facts = _noul(answers, "needs_outside_facts")
    judgment.visual = _noul(answers, "visual")
    judgment.same_target = _noul(answers, "same_target")
    return judgment


def final_target(judgment: Judgment, deterministic: str | None, pinned: str | None, previous_target: str | None,
                 known_ids: set[str]) -> str | None:
    if pinned and pinned in known_ids:
        return pinned
    if (previous_target and previous_target in known_ids and judgment.same_target is not None
            and judgment.same_target >= SAME_TARGET_MIN):
        return previous_target
    return judgment.target_id or deterministic


def judge(ctx: SpatialContext, resolution: dict, anchors: list[dict], previous_question: str | None = None,
          pinned: str | None = None) -> Judgment:
    state, questions, letters = build_request(ctx, resolution, anchors, previous_question, pinned=bool(pinned))
    result = system_one.evaluate(state, questions)
    if result.status != "ok":
        return Judgment(status=result.status, latency_ms=result.latency_ms)
    judgment = decide(result.answers, letters, deterministic_top(resolution))
    judgment.model, judgment.latency_ms = result.model, result.latency_ms
    return judgment
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_semantic.py -q` → all pass; `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/semantic.py server/tests/test_semantic.py
git commit -m "feat(server): semantic judgments — geometry wording, Jev request, hybrid/ambiguity/routing decisions"
```

---

### Task 3: Answer layer — mode line, vision switch, target-first prompt

**Files:**
- Modify: `server/app/providers.py`
- Test: `server/tests/test_providers_routing.py` (new)

**Interfaces:**
- Produces: `providers.MODE_HINTS: dict[str, str]`; `answer_stream(..., precomputed_ocr=None, mode: str | None = None, prefer_vision: bool | None = None)`; `build_prompt` puts an anchor with `is_target: True` first under "The user is asking about:" and the rest under "Nearby, probably not the target:"; meta gains `"mode"`.

- [ ] **Step 1: Failing tests** — `server/tests/test_providers_routing.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import providers  # noqa: E402
from app.config import ProviderConfig  # noqa: E402

ANCHORS = [{"id": "t", "type": "button", "text": "Edit", "is_target": True},
           {"id": "n", "type": "div", "text": "File Edit View"}]


def test_prompt_puts_target_first():
    prompt = providers.build_prompt("what does this do?", {"title": "App"}, ANCHORS, "", [])
    assert "The user is asking about:\n- [button] Edit" in prompt
    assert "Nearby, probably not the target:\n- [div] File Edit View" in prompt


def test_prompt_without_target_unchanged():
    prompt = providers.build_prompt("q", {"title": "App"}, [dict(ANCHORS[1])], "", [])
    assert "Text under the mark (ranked, most relevant first):" in prompt


def run(monkeypatch, **kwargs):
    fake = {"p": ProviderConfig("p", "https://example", "key", "text-model", "vision-model", "openai")}
    monkeypatch.setattr(providers.settings, "providers", fake, raising=False)
    monkeypatch.setattr(providers.settings, "provider_order", ("p",), raising=False)
    calls = []

    def fake_stream(config, prompt, image_data, use_vision=True):
        calls.append((use_vision, providers._system()))
        yield "ok"
        yield {"provider": "p", "model": "m", "vision": use_vision}

    monkeypatch.setattr(providers, "stream_provider", fake_stream)
    items = list(providers.answer_stream("q", {"title": "t"}, ANCHORS, "data:image/png;base64,AAAA", **kwargs))
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
    assert not any(h in calls[0][1] for h in providers.MODE_HINTS.values() if h) and meta["mode"] is None
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_providers_routing.py -q` → FAIL (no "The user is asking about", `MODE_HINTS` missing, unexpected kwargs).

- [ ] **Step 3: Implement in `providers.py`**

After `DIAGRAM_NOTE = …` add:

```python
# One extra system-prompt line per help mode (chosen by the System One judgment in app/semantic.py).
MODE_HINTS = {
    "explain": "Explain how or why, briefly.",
    "define": "Give the meaning in 1-2 sentences, then one short example.",
    "summarize": "Summarize in at most 3 short bullet points.",
    "compare": "Compare point by point: what is the same, then what differs.",
    "translate": "Translate faithfully, keep the formatting, add nothing else.",
    "debug_error": "Name the most likely cause first, then the fix.",
    "other": "",
}
```

Replace `_system()`:

```python
def _system() -> str:
    base = _SYSTEM_OVERRIDE.get("prompt", SYSTEM_PROMPT)
    level = _SYSTEM_OVERRIDE.get("level")
    mode_hint = MODE_HINTS.get(_SYSTEM_OVERRIDE.get("mode") or "", "")
    parts = [base, LEVELS[level] if level in LEVELS else "", mode_hint]
    return " ".join(part for part in parts if part)
```

In `build_prompt`, replace the `if anchors:` block with:

```python
    def anchor_line(item: dict[str, Any]) -> str:
        role = item.get("role")
        label = f"{role} · {item.get('type')}" if role and role != "reference" else str(item.get("type"))
        return f"- [{label}] {str(item.get('text', ''))[:500]}"

    if anchors and anchors[0].get("is_target"):
        lines.append("The user is asking about:")
        lines.append(anchor_line(anchors[0]))
        nearby = [item for item in anchors[1:8] if item.get("text")]
        if nearby:
            lines.append("Nearby, probably not the target:")
            lines += [anchor_line(item) for item in nearby]
    elif anchors:
        lines.append("Text under the mark (ranked, most relevant first):")
        lines += [anchor_line(item) for item in anchors[:8] if item.get("text")]
```

In `answer_stream`: add parameters after `precomputed_ocr`:

```python
    mode: str | None = None,
    prefer_vision: bool | None = None,
```

after the `_SYSTEM_OVERRIDE["level"] = …` line add `_SYSTEM_OVERRIDE["mode"] = mode if mode in MODE_HINTS else None`; change
`has_vision = bool(config.vision_model and image_data)` to
`has_vision = bool(config.vision_model and image_data) and prefer_vision is not False  # routing says "not visual"`;
add `"mode": _SYSTEM_OVERRIDE.get("mode"),` next to each `"level": _SYSTEM_OVERRIDE.get("level"),` in both meta dicts.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_providers_routing.py -q` → pass; `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/providers.py server/tests/test_providers_routing.py
git commit -m "feat(server): answer layer honours mode, vision routing and target-first prompt"
```

---

### Task 4: Wire judgments into the ask flow

**Files:**
- Modify: `server/app/main.py`, `server/app/trace.py`
- Test: `server/tests/test_semantic_flow.py` (new)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `Ask.target_id`; `prep` keys `judgment`, `target_id`, `pinned`, `clarify`, `prefer_vision`; response keys `routing` (dict or `None`), `clarify` (list), `system_one` (`{status, model, latency_ms}`); `resolution_v3` hybrid fields; stored answer record `target_id`; `trace.build_record(..., system_one=None, label=None)`; health `system_one`.

- [ ] **Step 1: Failing tests** — `server/tests/test_semantic_flow.py`:

```python
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
    "marks": [{"type": "rectangle", "role": "reference", "x": 100, "y": 100, "width": 300, "height": 120}],
    "anchors": [
        {"id": "big", "type": "p", "text": "A long paragraph about the export feature", "bbox": {"x": 100, "y": 100, "width": 300, "height": 120}},
        {"id": "btn", "type": "button", "text": "Export", "bbox": {"x": 120, "y": 120, "width": 60, "height": 20}},
        {"id": "far", "type": "p", "text": "footer", "bbox": {"x": 0, "y": 650, "width": 100, "height": 20}},
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
            answers = {"mode": {"choice": routing.get("mode", "explain")},
                       "needs_outside_facts": {"noul": routing.get("facts", 0.1)},
                       "visual": {"noul": routing.get("visual", 0.1)}}
            if "same_target" in questions:
                answers["same_target"] = {"noul": routing.get("same", 0.9)}
            if "target" in questions and target_text:
                first = letter[target_text]
                probs = {first: 0.9, "none": 0.1}
                if second:
                    probs = {first: 0.5, letter[second]: 0.45, "none": 0.05}
                answers["target"] = {"choice": first, "confidence": conf, "probabilities": probs}
            return system_one.Result("ok", answers, "jev-1.13.0", 470)
        monkeypatch.setattr(main.semantic.system_one, "evaluate", fake)

    gathered = []
    monkeypatch.setattr(research, "gather", lambda q, anchors, max_sources=4: gathered.append(q) or [])
    return install, sent, gathered


def test_hybrid_target_routing_and_research_gate(jev):
    install, _, gathered = jev
    install(target_text="Export", mode="define", facts=0.1)
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json=BASE).json()
    assert body["anchors_used"][0]["id"] == "btn" and body["anchors_used"][0]["is_target"] is True
    assert body["resolution_v3"]["selected_candidate_id"] == "btn"
    assert body["resolution_v3"]["resolver"] == "hybrid-jev-1.13.0" and body["resolution_v3"]["semantic_confidence"] == 0.9
    assert body["routing"]["mode"] == "define" and body["clarify"] == []
    assert body["system_one"]["status"] == "ok" and gathered == []  # research skipped: no outside facts needed


def test_research_runs_when_facts_needed(jev):
    install, _, gathered = jev
    install(target_text="Export", facts=0.95)
    with TestClient(main.app) as client:
        client.post("/api/ask", json=BASE)
    assert gathered == ["what does this do?"]


def test_ambiguous_returns_clarify(jev):
    install, _, _ = jev
    install(target_text="Export", conf=0.2, second="A long paragraph about the export feature")
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json=BASE).json()
    assert [c["id"] for c in body["clarify"]] == ["btn", "big"] and body["confirmation_required"] is True
    assert body["resolution_v3"]["abstained"] is True


def test_jev_failure_is_todays_behaviour(jev, monkeypatch):
    _, _, gathered = jev
    monkeypatch.setattr(main.semantic.system_one, "evaluate", lambda s, q: system_one.Result("timeout", latency_ms=1500))
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json=BASE).json()
    assert body["routing"] is None and body["clarify"] == [] and body["system_one"]["status"] == "timeout"
    assert body["resolution_v3"]["resolver"] == "structured-anchor-v1" and gathered == ["what does this do?"]


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
    # mark bottom at y=655 overlaps 5 of the footer's 20 px: score ~0.24 → shortlisted (>= 0.10) but below the 0.25 cut
    marks = [{"type": "rectangle", "role": "reference", "x": 0, "y": 100, "width": 400, "height": 555}]
    with TestClient(main.app) as client:
        body = client.post("/api/ask", json={**BASE, "marks": marks}).json()
    assert body["anchors_used"][0]["id"] == "far" and body["anchors_used"][0]["is_target"] is True


def test_followup_keeps_previous_target(jev):
    install, sent, _ = jev
    install(target_text="Export")
    with TestClient(main.app) as client:
        first = client.post("/api/ask", json=BASE).json()
        install(target_text="A long paragraph about the export feature", same=0.9)
        second = client.post("/api/ask", json={**BASE, "question": "and why?", "context_id": first["id"]}).json()
    assert "same_target" in sent["questions"] and second["anchors_used"][0]["id"] == "btn"


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
    assert record["system_one"]["status"] == "ok" and record["label"] == "btn" and "secret-key-xyz" not in raw


def test_health_reports_system_one():
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["system_one"]["backend"] == "off"
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_semantic_flow.py -q` → FAIL (`module 'app.main' has no attribute 'semantic'`).

- [ ] **Step 3: `main.py` changes**

Imports: `from contextlib import asynccontextmanager`, `import threading`, `from app import research, semantic, system_one, trace` (replace the `research, trace` import).

Before `app = FastAPI(...)`:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Open the System One TLS connection early; never blocks startup.
    threading.Thread(target=system_one.warm, daemon=True).start()
    yield


```

and pass `lifespan=lifespan` to `FastAPI(...)`.

`Ask`: add `target_id: str | None = Field(default=None, max_length=200)  # "Did you mean" chip: pin this candidate`.

Health: add `"system_one": system_one.status(),`.

Add helper after `anchors_used`:

```python
def promote_target(used: list[dict], target_id: str | None, anchors: list[dict]) -> list[dict]:
    """Put the chosen target first (even if its geometric score fell below the anchors_used cut) and mark it."""
    if not target_id:
        return used
    rest = [item for item in used if item["id"] != target_id]
    chosen = next((item for item in used if item["id"] == target_id), None)
    if chosen is None:
        source = next((a for a in anchors if a["id"] == target_id), None)
        if source is None:
            return used
        chosen = {"id": source["id"], "type": source.get("type"), "text": str(source.get("text") or "")[:1500],
                  "score": 0.0, "page": source.get("page"), "href": str(source.get("href") or "")[:500],
                  "src": str(source.get("src") or "")[:500], "role": "reference", "mark_index": 0,
                  "bbox": source.get("bbox")}
    return [{**chosen, "is_target": True}, *rest]
```

In `prepare_ask`, replace from `used = anchors_used(resolution, anchors)` through the `sources = …` / research timing lines with:

```python
    used = anchors_used(resolution, anchors)
    previous_answer = (previous or {}).get("answer", {})
    history = previous_answer.get("history", [])
    known_ids = {a["id"] for a in anchors}
    pinned = payload.target_id if payload.target_id in known_ids else None
    judge_started = perf_counter()
    judgment = semantic.judge(ctx, resolution, anchors,
                              previous_question=history[-1]["question"] if history else None, pinned=pinned)
    timings["system_one"] = round((perf_counter() - judge_started) * 1000)
    target_id = semantic.final_target(judgment, semantic.deterministic_top(resolution), pinned,
                                      previous_answer.get("target_id"), known_ids)
    used = promote_target(used, target_id, anchors)
    judged = judgment.status == "ok"
    allow_research = payload.research
    if allow_research and judged and judgment.needs_outside_facts is not None:
        allow_research = judgment.needs_outside_facts >= semantic.FACTS_MIN
    prefer_vision = (judgment.visual >= semantic.VISUAL_MIN) if judged and judgment.visual is not None else None
    by_id = {a["id"]: a for a in anchors}
    clarify = [{"id": cid, "text": str(by_id[cid].get("text") or "")[:200], "bbox": by_id[cid].get("bbox")}
               for cid in judgment.clarify_ids if cid in by_id] if judgment.ambiguous and not pinned else []
    research_started = perf_counter()
    sources = research.gather(ctx.question, used) if allow_research else []
    timings["research"] = round((perf_counter() - research_started) * 1000)
```

and add to the returned prep dict: `"judgment": judgment, "target_id": target_id, "pinned": pinned, "clarify": clarify, "prefer_vision": prefer_vision,`.

In both `answer_stream(...)` calls add keyword arguments `mode=prep["judgment"].mode, prefer_vision=prep["prefer_vision"],`.

In `finish_ask`: add `"target_id": prep["target_id"],` to `record`; replace `semantic = to_semantic_resolution(resolution)` (the local name clashes with the module) with:

```python
    judgment = prep["judgment"]
    semantic_resolution = to_semantic_resolution(resolution)
    if judgment.status == "ok":
        alternatives = [Alternative(candidate_id=cid, score=round(p, 4))  # model_copy(update=) does not validate
                        for cid, p in sorted(judgment.probabilities.items(), key=lambda kv: -kv[1])]
        semantic_resolution = semantic_resolution.model_copy(update={
            "selected_candidate_id": prep["target_id"], "semantic_confidence": judgment.semantic_confidence,
            "abstained": judgment.ambiguous if judgment.asked_target else semantic_resolution.abstained,
            "resolver": f"hybrid-{judgment.model or 'jev'}",
            **({"alternatives": alternatives} if alternatives else {}),
        })
    elif prep["target_id"]:
        semantic_resolution = semantic_resolution.model_copy(update={"selected_candidate_id": prep["target_id"]})
    system_one_meta = {"status": judgment.status, "model": judgment.model, "latency_ms": judgment.latency_ms}
```

Add `Alternative` to the `from app.contracts import (...)` list in `main.py`.

Rename every later use of the old local `semantic` in `finish_ask` to `semantic_resolution`. Response dict additions:

```python
        "routing": ({"mode": judgment.mode, "needs_outside_facts": judgment.needs_outside_facts,
                     "visual": judgment.visual, "same_target": judgment.same_target}
                    if judgment.status == "ok" else None),
        "clarify": prep["clarify"],
        "system_one": system_one_meta,
```

and `"confirmation_required": (judgment.ambiguous if judgment.status == "ok" and judgment.asked_target else resolution["confidence"] < 0.6),`. In the trace block add `system_one={**system_one_meta, "answers_used": {"mode": judgment.mode, "needs_outside_facts": judgment.needs_outside_facts, "visual": judgment.visual, "same_target": judgment.same_target, "probabilities": judgment.probabilities}}, label=prep["pinned"],` to `trace.build_record(...)`; add `"system_one"` to timings keys automatically (already in `prep["timings"]`).

`trace.build_record`: add keyword parameters `system_one: dict | None = None, label: str | None = None` and record keys `"system_one": system_one, "label": label,` (inside the `_scrub({...})`).

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_semantic_flow.py -q` → all pass; `python -m pytest -q` → all pass (existing tests run with System One off → today's behaviour).

- [ ] **Step 5: Commit**

```bash
git add server/app/main.py server/app/trace.py server/tests/test_semantic_flow.py
git commit -m "feat(server): hybrid target, ambiguity chips data, research/vision routing from one Jev request"
```

---

### Task 5: Hybrid eval with a recorded cassette

**Files:**
- Modify: `server/app/evaluation.py`, `scripts/eval.py`
- Create: `server/tests/system_one_cassette.json` (recorded live once), extend `server/tests/test_evaluation.py`

**Interfaces:**
- Produces: `evaluation.run_case_hybrid(case, cassette: dict, record: bool = False) -> dict` (same keys as `run_case` plus `flagged_ambiguous`); `evaluation.load_cassette(path) -> dict`, `evaluation.save_cassette(path, cassette)`; CLI `--resolver geometry|hybrid`, `--record`.

- [ ] **Step 1: Failing tests** — append to `server/tests/test_evaluation.py`:

```python
CASSETTE = TESTS / "system_one_cassette.json"


def test_hybrid_replays_cassette_and_beats_geometry():
    cassette = evaluation.load_cassette(CASSETTE)
    cases = [c for c in evaluation.load_cases(DIRS) if not c.get("multi")]
    hybrid = [evaluation.run_case_hybrid(c, cassette) for c in cases]
    geometry = [evaluation.run_case(c) for c in cases]
    assert sum(r["top1"] for r in hybrid) >= sum(r["top1"] for r in geometry)
    assert sum(r["top1"] for r in hybrid) >= 47


def test_hybrid_without_cassette_entry_asks_to_record():
    case = evaluation.load_cases(DIRS)[0]
    with pytest.raises(KeyError, match="--record"):
        evaluation.run_case_hybrid(case, {})
```

(add `import pytest` at the top of the file.)

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_evaluation.py -q` → FAIL (`load_cassette` missing).

- [ ] **Step 3: `evaluation.py` additions**

```python
from app import semantic, system_one


def load_cassette(path: Path) -> dict:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cassette(path: Path, cassette: dict) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(cassette, indent=1, sort_keys=True) + "\n")


def run_case_hybrid(case: dict, cassette: dict, record: bool = False) -> dict:
    """Same scoring as run_case, but the target is the System One hybrid decision (answers replayed from cassette)."""
    if case.get("multi"):
        return {**run_case(case), "flagged_ambiguous": False}
    ctx = from_v2(question=case["question"], marks=case["marks"], anchors=case["anchors"], canvas=case["canvas"],
                  page={"surface": case["surface"]}, privacy_policy="anchors_only")
    marks, canvas, anchors = resolver_inputs(ctx)
    started = perf_counter()
    resolution = resolve_marks(marks, canvas, anchors)
    state, questions, letters = semantic.build_request(ctx, resolution, anchors)
    key = semantic.request_key(state, questions)
    if key not in cassette:
        if not record:
            raise KeyError(f"no cassette entry for {case['name']}; run: python scripts/eval.py cases --resolver hybrid --record")
        result = system_one.evaluate(state, questions)
        if result.status != "ok":
            raise RuntimeError(f"System One {result.status} while recording {case['name']}")
        cassette[key] = result.answers
    judgment = semantic.decide(cassette[key], letters, semantic.deterministic_top(resolution))
    latency = (perf_counter() - started) * 1000
    geometric = [item["id"] for item in (resolution["candidates"] or [{}])[0].get("anchors_ranked", [])]
    by_prob = sorted(judgment.probabilities, key=judgment.probabilities.get, reverse=True)
    order = [cid for cid in dict.fromkeys([judgment.target_id, *by_prob, *geometric]) if cid]
    intended = case["intended"]
    if intended == [None]:
        top1 = top3 = judgment.target_id is None
    else:
        top1 = judgment.target_id in intended
        top3 = any(cid in intended for cid in order[:3])
    return {"name": case["name"], "category": case["category"], "top1": top1, "top3": top3,
            "abstained": judgment.ambiguous, "flagged_ambiguous": judgment.ambiguous, "latency_ms": latency,
            "predicted": [judgment.target_id] if judgment.target_id else [], "confidence": judgment.semantic_confidence}
```

- [ ] **Step 4: `scripts/eval.py`** — add arguments `--resolver` (choices `geometry`, `hybrid`; default `geometry`) and `--record`; in `cases` mode:

```python
    cassette_path = TESTS / "system_one_cassette.json"
    if args.mode == "cases":
        cases = evaluation.load_cases([TESTS / "cases", TESTS / "eval_cases"])
        if args.resolver == "hybrid":
            cassette = evaluation.load_cassette(cassette_path)
            results = [evaluation.run_case_hybrid(c, cassette, record=args.record) for c in cases]
            if args.record:
                evaluation.save_cassette(cassette_path, cassette)
        else:
            results = [evaluation.run_case(c) for c in cases]
```

(The `--record` path needs the real key: `scripts/eval.py` imports `app.config`, which loads `server/.env`.)

- [ ] **Step 5: Record and run**

Run (repo root, live, ~50 requests ≈ $0.0015): `python scripts/eval.py cases --resolver hybrid --record`
Expected: prints hybrid metrics; `server/tests/system_one_cassette.json` written. Record the printed numbers in `docs/MEMORY.md`.
Then `python scripts/eval.py cases --resolver hybrid` (offline replay) → same numbers.
Run (from `server/`): `python -m pytest -q` → all pass. If hybrid top-1 < 47: stop, inspect misses (state/questions/answers per the TypeSafe skill's "inspect the exact state…" guidance), and ledger a ruling before changing wording or thresholds.

- [ ] **Step 6: Commit**

```bash
git add server/app/evaluation.py scripts/eval.py server/tests/test_evaluation.py server/tests/system_one_cassette.json
git commit -m "feat: hybrid System One eval with recorded cassette"
```

---

### Task 6: Extension — "Did you mean" chips + research label

**Files:**
- Modify: `extension/content.js`, `extension/popup.html`

**Interfaces:**
- Consumes: response `clarify: [{id, text, bbox}]`, request field `target_id`.

- [ ] **Step 1: Write the change**

`content.js`:

1. `state` initializer: add `pinTarget: null`.
2. CSS template: after the `.ring-static { … }` rule add:
   ```css
       .ring-choice { fill: rgba(47,124,246,.08); stroke: ${TARGET}; stroke-width: 2; stroke-dasharray: 6 4; }
       .ring-label { fill: ${TARGET}; font: 700 14px system-ui, sans-serif; }
       .a .clarify { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 6px; font-size: 12px; color: #6b6b7b; }
       .a .clarify button { all: unset; cursor: pointer; font-size: 12px; padding: 3px 8px; border-radius: 6px; background: #eaf1fe; color: #17171c; }
       .a .clarify button:hover { background: #d8e6fd; }
   ```
   (`TARGET` is the existing `#2f7cf6` constant; if the file names it differently, use that constant.)
3. In `highlightAnchors`, also remove `.ring-choice, .ring-label` nodes at the top: `svg.querySelectorAll('.ring, .ring-static, .ring-choice, .ring-label')`.
4. New function next to `highlightAnchors`:
   ```js
   /* Ambiguous mark: number the plausible targets on the page and offer them as chips. */
   function attachClarify(answerNode, clarify, question, input, thread, sendButton) {
     const row = el('div', { class: 'clarify' }, ['Did you mean:']);
     clarify.forEach((choice, index) => {
       const n = String(index + 1);
       if (choice.bbox) {
         const b = choice.bbox;
         svg.append(svgNode('rect', { class: 'ring-choice', x: b.x - 3, y: b.y - 3, width: b.width + 6, height: b.height + 6, rx: 6 }));
         const label = svgNode('text', { class: 'ring-label', x: b.x - 2, y: Math.max(14, b.y - 6) });
         label.textContent = n;
         svg.append(label);
       }
       const text = (choice.text || '').trim();
       const button = el('button', { title: text }, [n + '. ' + (text.length > 40 ? text.slice(0, 39) + '…' : text || 'this')]);
       button.onclick = () => { state.pinTarget = choice.id; input.value = question; submit(input, thread, sendButton); };
       row.append(button);
     });
     answerNode.insertBefore(row, answerNode.querySelector('small'));
   }
   ```
5. In `submit`, add to the payload object: `target_id: state.pinTarget,` and right after the payload literal: `state.pinTarget = null;`.
6. Replace `if (result.confirmation_required) note.push('low confidence – circle tighter?');` with
   `if (result.confirmation_required && !(result.clarify || []).length) note.push('low confidence – circle tighter?');`
7. After `highlightAnchors(result.anchors_used);` add:
   `if ((result.clarify || []).length >= 2) attachClarify(answerNode, result.clarify, question, input, thread, sendButton);`
8. Status texts no longer promise research: in `state.onStatus` replace `(state.settings.research !== false ? 'checking sources…' : 'asking…')` with `'thinking…'`, and replace `if (state.settings.research !== false) answerNode.textContent = 'Searching sources for what you marked…';` with nothing (delete the line).

`popup.html`: research label text → `Verify with sources when needed (~5 s when used)`.

- [ ] **Step 2: Verify**

Run (repo root): `node --check extension/content.js` → no output; `node --test extension/tests/geometry.test.mjs` → pass.
Manual (with server running and Jev enabled): circle two adjacent paragraphs equally → chips "1." / "2." appear with numbered dashed outlines; clicking a chip re-asks and the answer is about that paragraph.

- [ ] **Step 3: Commit**

```bash
git add extension/content.js extension/popup.html
git commit -m "feat(extension): 'Did you mean' chips with numbered outlines; research runs when needed"
```

---

### Task 7: Docs

**Files:** `docs/ARCHITECTURE.md`, `docs/AGENTS.md`, `docs/DESIGN.md`, `docs/TASKS.md`, `docs/MEMORY.md`, `docs/PRD.md`, spec status.

- [ ] **Step 1:** Use the `/sync-docs` routine:
  - ARCHITECTURE §1 ask flow: add "System One judgment (Jev) after resolution: hybrid target, ambiguity → clarify chips, research only when outside facts are needed, vision only when visual; any failure → geometry-only".
  - AGENTS: test count (real run), `python scripts/eval.py cases --resolver hybrid [--record]`, settings `SPATIAL_SYSTEM_ONE*`.
  - DESIGN decision log row: "2026-09-23 — Clarify chips instead of 'circle tighter'; Jev on every ask (option a)".
  - PRD G2: resolution budget now "≤ 1.5 s incl. System One (≈0.5 s warm); research skipped when not needed".
  - TASKS: sub-project 2 items done; MEMORY: hybrid eval numbers from Task 5.
  - Spec status → Implemented.
- [ ] **Step 2:** Run `python -m pytest -q` (server) and `node --test extension/tests/geometry.test.mjs`; commit:

```bash
git add docs
git commit -m "docs: System One resolver shipped; tasks, memory, architecture, design"
```
