"""Spatial's System One judgments: one Jev request per ask decides which object was meant and how to answer.
Geometry stays in code and reaches Jev as words (numbers cost 7 points of accuracy in the spike). Wording and
thresholds come from docs/TYPESAFE_OPPORTUNITIES.md -> Results and the recorded eval (hybrid 49/49 single-mark cases)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app import system_one
from app.contracts import SpatialContext, mark_to_v2

logger = logging.getLogger("spatial.semantic")
# Never send pixels to a third party: data: URLs anywhere in a string, and long base64-looking runs.
_DATA_URL = re.compile(r"data:[\w.+-]+/[\w.+-]+[;,][^\s\"']*", re.I)
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{100,}")


def _clean(value: Any, limit: int) -> str:
    text = str(value or "")
    text = _BASE64_RUN.sub("[binary]", _DATA_URL.sub("[image]", text))
    return text[:limit]


# Take Jev's pick when it is more likely than not. Gating on `confidence` instead lost 2/49 eval cases: with
# several options plus `none`, confidence is diluted even when the pick is clearly preferred (p=0.55-0.62).
TARGET_MIN_PROB = 0.5
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
    return (
        outer["x"] <= inner["x"]
        and outer["y"] <= inner["y"]
        and outer["x"] + outer["width"] >= inner["x"] + inner["width"]
        and outer["y"] + outer["height"] >= inner["y"] + inner["height"]
        and _area(outer) > _area(inner)
    )


def mark_phrase(mark: dict) -> str:
    kind = mark["type"]
    if kind == "point":
        return "a single click on one spot"
    if kind == "polygon":
        return (
            "an open stroke, like an underline"
            if mark.get("closed") is False
            else "a freehand loop drawn around something"
        )
    return {
        "rectangle": "a box dragged around something",
        "circle": "an ellipse dragged around something",
    }.get(kind, kind)


def relation(box: dict, mark: dict) -> dict[str, str]:
    if mark["type"] == "point":
        x, y = mark["x"], mark["y"]
        on = (
            box["x"] <= x <= box["x"] + box["width"]
            and box["y"] <= y <= box["y"] + box["height"]
        )
        return {
            "position": "the clicked spot is on this element"
            if on
            else "the clicked spot is not on this element"
        }
    points = mark.get("points") or []
    if mark["type"] == "polygon" and mark.get("closed") is False and points:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        line_y, left, right = sum(ys) / len(ys), min(xs), max(xs)
        under = max(
            0.0, min(right, box["x"] + box["width"]) - max(left, box["x"])
        ) / max(1.0, right - left)
        gap = line_y - (box["y"] + box["height"])
        if under >= 0.5 and 0 <= gap <= 16:
            return {
                "position": "the stroke is drawn directly under this element, like an underline"
            }
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
    size = (
        "much larger than the marked area"
        if ratio > 3
        else "much smaller than the marked area"
        if ratio < 0.33
        else "about the size of the marked area"
    )
    return {"position": position, "size": size}


# --- request ------------------------------------------------------------------------------------------------


def deterministic_top(resolution: dict) -> str | None:
    first = (resolution.get("candidates") or [{}])[0]
    return first.get("anchor_id")


def build_request(
    ctx: SpatialContext,
    resolution: dict,
    anchors: list[dict],
    previous_question: str | None = None,
    pinned: bool = False,
) -> tuple[dict, dict, dict[str, str]]:
    first = (resolution.get("candidates") or [{}])[0]
    by_id = {a["id"]: a for a in anchors}
    ranked = [
        item["id"] for item in first.get("anchors_ranked", []) if item["id"] in by_id
    ][:MAX_SHORTLIST]
    mark = mark_to_v2(ctx.marks[0])
    letters = dict(zip(LETTERS, ranked))
    elements: dict[str, dict] = {}
    for letter, cid in letters.items():
        box = by_id[cid]["bbox"]
        element = {
            "kind": _clean(by_id[cid].get("type"), 40) or "element",
            "text": _clean(by_id[cid].get("text"), 300) or "(no text)",
            **relation(box, mark),
        }
        inside = [
            l2
            for l2, c2 in letters.items()
            if l2 != letter and _contains(by_id[c2]["bbox"], box)
        ]
        contains = [
            l2
            for l2, c2 in letters.items()
            if l2 != letter and _contains(box, by_id[c2]["bbox"])
        ]
        if inside:
            element["inside_elements"] = inside
        if contains:
            element["contains_elements"] = contains
        elements[letter] = element
    top = by_id.get(ranked[0]) if ranked else None
    state: dict[str, Any] = {
        "user_question": _clean(ctx.question, 2000),
        "mark": mark_phrase(mark),
        "screen": {"pdf": "a PDF document", "desktop": "an application window"}.get(
            ctx.surface.kind, "a web page"
        ),
        "elements": elements,
        "marked": {
            "kind": _clean((top or {}).get("type"), 40) or "image region",
            "text": _clean((top or {}).get("text"), 300) or "(no text)",
        },
    }
    if previous_question:
        state["previous_question_in_this_conversation"] = _clean(previous_question, 300)
    questions: dict[str, Any] = {
        "mode": {
            "type": "choice",
            "instructions": "What kind of help does the user want for the marked thing?",
            "criteria": MODES,
        },
        "needs_outside_facts": {
            "type": "noul",
            "instructions": "Does answering `user_question` well require facts that "
            "are not in `marked` and may be current or specific (dates, people, prices, versions, "
            "whether a claim is still true)?",
        },
        "visual": {
            "type": "noul",
            "instructions": "Is the marked thing mainly visual (a chart, diagram, image, icon or "
            "UI layout) so that the answer needs to see it rather than read its text?",
        },
    }
    if letters and not pinned:
        criteria = {
            letter: f"element {letter}: {el['kind']} “{el['text'][:80]}”"
            for letter, el in elements.items()
        }
        criteria["none"] = "none of the listed elements is what the user marked"
        questions["target"] = {
            "type": "choice",
            "criteria": criteria,
            "instructions": "The user marked part of the screen (`mark`) and asked `user_question`. "
            "Which one element in `elements` is the user referring to?",
        }
    if previous_question:
        questions["same_target"] = {
            "type": "noul",
            "instructions": "Is `user_question` about the same marked thing as "
            "`previous_question_in_this_conversation`, rather than a new thing?",
        }
    return state, questions, letters


def request_key(state: dict, questions: dict) -> str:
    return hashlib.sha256(
        json.dumps([state, questions], sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()


# --- decisions ----------------------------------------------------------------------------------------------


def _obj(answers: dict, key: str) -> dict:
    value = answers.get(key)
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _noul(answers: dict, key: str) -> float | None:
    return _num(_obj(answers, key).get("noul"))


def decide(
    answers: dict, letters: dict[str, str], deterministic: str | None
) -> Judgment:
    judgment = Judgment(status="ok", target_id=deterministic)
    answers = answers if isinstance(answers, dict) else {}
    target = _obj(answers, "target")
    if target and letters:
        judgment.asked_target = True
        raw = (
            target.get("probabilities")
            if isinstance(target.get("probabilities"), dict)
            else {}
        )
        probs = {
            letters[letter]: _num(p)
            for letter, p in raw.items()
            if letter in letters and _num(p) is not None
        }
        judgment.probabilities = probs
        choice = target.get("choice")
        picked = letters.get(choice) if isinstance(choice, str) else None
        judgment.semantic_confidence = _num(target.get("confidence"))
        if picked and probs.get(picked, 0.0) >= TARGET_MIN_PROB:
            judgment.target_id = picked
        ordered = sorted(probs.values(), reverse=True)
        close = (
            len(ordered) > 1
            and ordered[0] > 0
            and ordered[1] / ordered[0] >= AMBIGUITY_RATIO
        )
        judgment.ambiguous = picked is None or close
        if judgment.ambiguous:
            ranked = sorted(probs, key=probs.get, reverse=True)
            judgment.clarify_ids = ranked[:4] if len(ranked) >= 2 else []
    mode = _obj(answers, "mode").get("choice")
    judgment.mode = mode if isinstance(mode, str) and mode in MODES else None
    judgment.needs_outside_facts = _noul(answers, "needs_outside_facts")
    judgment.visual = _noul(answers, "visual")
    judgment.same_target = _noul(answers, "same_target")
    return judgment


def final_target(
    judgment: Judgment,
    deterministic: str | None,
    pinned: str | None,
    previous_target: str | None,
    known_ids: set[str],
) -> str | None:
    if pinned and pinned in known_ids:
        return pinned
    if (
        previous_target
        and previous_target in known_ids
        and judgment.same_target is not None
        and judgment.same_target >= SAME_TARGET_MIN
    ):
        return previous_target
    return judgment.target_id or deterministic


def judge(
    ctx: SpatialContext,
    resolution: dict,
    anchors: list[dict],
    previous_question: str | None = None,
    pinned: str | None = None,
) -> Judgment:
    """Never raises: any failure (transport, schema drift, a bug here) means geometry-only for this ask."""
    try:
        state, questions, letters = build_request(
            ctx, resolution, anchors, previous_question, pinned=bool(pinned)
        )
        result = system_one.evaluate(state, questions)
        if result.status != "ok":
            return Judgment(status=result.status, latency_ms=result.latency_ms)
        judgment = decide(result.answers, letters, deterministic_top(resolution))
        judgment.model, judgment.latency_ms = result.model, result.latency_ms
        return judgment
    except Exception as exc:
        logger.warning("system one judgment failed: %s", type(exc).__name__)
        return Judgment(status="error")


# --- research: passage ranking (E3) and citation check (live judge) -----------------------------------------

PASSAGE_MIN = 1.5  # expected level on the 0-3 relevance scale below
MAX_PASSAGES = 12
PASSAGE_LEVELS = [
    "irrelevant to the question",
    "same topic but does not help answer the question",
    "partly answers the question",
    "directly answers the question",
]
VERDICTS = {
    "supports": "the source text states or directly implies the claim",
    "partly": "the source supports part of the claim but not all of it",
    "unrelated": "the source does not address the claim",
    "contradicts": "the source says something that conflicts with the claim",
}
_CITE = re.compile(r"\[(\d{1,2})\]")


def rank_passages(question: str, marked: str, sources: list[dict]) -> list[dict] | None:
    """Score every passage with Jev; keep relevant ones (max 2 per source), best source first.
    None when there is nothing to rank or System One gave nothing usable (caller keeps search order)."""
    try:
        flat = [
            (si, passage)
            for si, source in enumerate(sources)
            for passage in source.get("passages", [])
        ]
        flat = flat[:MAX_PASSAGES]
        if not flat:
            return None
        state = {
            "question": _clean(question, 2000),
            "marked": _clean(marked, 600),
            "passages": {f"P{k + 1}": _clean(p, 600) for k, (_, p) in enumerate(flat)},
        }
        questions = {
            f"P{k + 1}": {
                "type": "score",
                "criteria": PASSAGE_LEVELS,
                "instructions": f"How well does `passages.P{k + 1}` help answer `question` "
                f"about the marked text `marked`?",
            }
            for k in range(len(flat))
        }
        result = system_one.evaluate(state, questions)
        if result.status != "ok":
            return None
        scores = {
            k: _num(_obj(result.answers, f"P{k + 1}").get("score"))
            for k in range(len(flat))
        }
        if all(v is None for v in scores.values()):
            return None
        kept: dict[int, list[tuple[float, str]]] = {}
        for k, (si, passage) in enumerate(flat):
            score = scores[k]
            if score is not None and score >= PASSAGE_MIN:
                kept.setdefault(si, []).append((score, passage))
        ranked = sorted(
            kept.items(),
            key=lambda item: (
                -max(s for s, _ in item[1]),
                -sources[item[0]].get("credibility", 0.0),
            ),
        )
        return [
            {
                **sources[si],
                "passages": [p for _, p in sorted(items, key=lambda x: -x[0])[:2]],
            }
            for si, items in ranked
        ]
    except Exception as exc:
        logger.warning("passage ranking failed: %s", type(exc).__name__)
        return None


def check_citations(answer: str, sources: list[dict]) -> tuple[list[dict], list[int]]:
    """For each (sentence, cited source) pair ask Jev whether the source supports it.
    Returns (checks, unsupported source ids); ([], []) when there is nothing to check or System One is down."""
    try:
        by_id = {s["id"]: s for s in sources}
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", (answer or "").strip()) if s]
        pairs = []
        for index, sentence in enumerate(sentences):
            for ref in dict.fromkeys(int(n) for n in _CITE.findall(sentence)):
                if ref in by_id:
                    pairs.append((index, ref))
        pairs = pairs[:MAX_PASSAGES]
        if not pairs:
            return [], []
        used = sorted({ref for _, ref in pairs})
        state = {
            "sentences": {
                f"S{i + 1}": _clean(_CITE.sub("", sentences[i]), 400)
                for i in {i for i, _ in pairs}
            },
            "sources": {
                f"src{ref}": _clean(" ".join(by_id[ref].get("passages", [])), 1200)
                for ref in used
            },
        }
        questions = {
            f"C{k + 1}": {
                "type": "choice",
                "criteria": VERDICTS,
                "instructions": f"Does `sources.src{ref}` support the claim in `sentences.S{i + 1}`?",
            }
            for k, (i, ref) in enumerate(pairs)
        }
        result = system_one.evaluate(state, questions)
        if result.status != "ok":
            return [], []
        checks, unsupported = [], set()
        for k, (i, ref) in enumerate(pairs):
            answer_k = _obj(result.answers, f"C{k + 1}")
            verdict = (
                answer_k.get("choice") if answer_k.get("choice") in VERDICTS else None
            )
            if verdict is None:
                continue
            probs = (
                answer_k.get("probabilities")
                if isinstance(answer_k.get("probabilities"), dict)
                else {}
            )
            probability = _num(probs.get(verdict))
            checks.append(
                {
                    "sentence_index": i,
                    "source_id": ref,
                    "verdict": verdict,
                    "probability": probability,
                }
            )
            if verdict in {"unrelated", "contradicts"} and (probability or 0.0) >= 0.5:
                unsupported.add(ref)
        return checks, sorted(unsupported)
    except Exception as exc:
        logger.warning("citation check failed: %s", type(exc).__name__)
        return [], []
