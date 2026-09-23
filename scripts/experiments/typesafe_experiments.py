"""Sub-project 2 spike: can Jev (TypeSafe System One) improve Spatial's resolution and routing?

E1  target selection + ambiguity over the 50 eval cases (golden + generated), one request per case:
    Choice "which element?" (+ none) and Noul "could it be two or more elements?".
    Variant `qual`: geometry described in words (computed in code). Variant `num`: raw overlap numbers.
E2  routing on 40 hand-labelled asks, one request each: help mode (Choice), needs outside facts (Noul),
    mainly visual (Noul), follow-up about the same thing (Noul).

Usage (repo root):  python scripts/experiments/typesafe_experiments.py [e1|e2|all]
Reads TYPESAFE_API_KEY from server/.env (never printed). Writes scripts/experiments/results/*.json.
Experimental code: its job is to produce numbers for a decision, not to ship."""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
load_dotenv(ROOT / "server" / ".env")

from app import evaluation  # noqa: E402
from app.contracts import from_v2, resolver_inputs  # noqa: E402
from app.resolver import resolve_marks  # noqa: E402

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
KEY = os.environ.get("TYPESAFE_API_KEY", "")
OUT = Path(__file__).parent / "results"
LETTERS = "ABCDEFGHIJKL"
VARIANTS = tuple(os.environ.get("E1_VARIANTS", "qual,num").split(","))
PRICE_PER_TOKEN = 0.042 / 1_000_000


def ask(state, questions, retries=3):
    body = {"model": MODEL, "state": state, "questions": questions}
    for attempt in range(retries):
        started = time.perf_counter()
        response = httpx.post(
            URL, json=body, headers={"Authorization": f"Bearer {KEY}"}, timeout=60
        )
        latency = (time.perf_counter() - started) * 1000
        if response.status_code == 429 and attempt < retries - 1:
            time.sleep(2**attempt)
            continue
        response.raise_for_status()
        data = response.json()
        return data["answers"], data.get("usage", {}), latency
    raise RuntimeError("unreachable")


# --- E1: target selection -----------------------------------------------------------------------------------


def _area(b):
    return max(0.0, b["width"]) * max(0.0, b["height"])


def _inter(a, b):
    w = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    return w * h if w > 0 and h > 0 else 0.0


def _contains(outer, inner):
    return (
        outer["x"] <= inner["x"]
        and outer["y"] <= inner["y"]
        and outer["x"] + outer["width"] >= inner["x"] + inner["width"]
        and outer["y"] + outer["height"] >= inner["y"] + inner["height"]
        and _area(outer) > _area(inner)
    )


def mark_shape(mark: dict) -> str:
    kind = mark["type"]
    if kind == "point":
        return "a single click on one spot"
    if kind == "polygon":
        return (
            "a freehand loop drawn around something"
            if mark.get("closed", True)
            else "an open stroke, like an underline"
        )
    return {
        "rectangle": "a box dragged around something",
        "circle": "an ellipse dragged around something",
    }.get(kind, kind)


def relation_words(c, m, is_point):
    if is_point:
        cx, cy = m["x"], m["y"]
        inside = (
            c["x"] <= cx <= c["x"] + c["width"] and c["y"] <= cy <= c["y"] + c["height"]
        )
        return {
            "position": "the clicked spot is on this element"
            if inside
            else "the clicked spot is not on this element"
        }
    inter = _inter(c, m)
    share_of_candidate = inter / _area(c) if _area(c) else 0
    share_of_mark = inter / _area(m) if _area(m) else 0
    if share_of_candidate >= 0.95:
        pos = "entirely inside the marked area"
    elif share_of_candidate >= 0.6:
        pos = "mostly inside the marked area"
    elif share_of_candidate >= 0.2:
        pos = "partly inside the marked area"
    else:
        pos = "only slightly overlaps the marked area"
    if share_of_mark >= 0.9 and share_of_candidate < 0.95:
        pos += "; it covers the whole marked area"
    ratio = _area(c) / _area(m) if _area(m) else 1
    size = (
        "much larger than the marked area"
        if ratio > 3
        else "much smaller than the marked area"
        if ratio < 0.33
        else "about the size of the marked area"
    )
    return {"position": pos, "size": size}


def relation_stroke(c, raw_mark):
    """Open strokes are pointers, not regions: describe where each element sits relative to the stroke line."""
    pts = raw_mark.get("points") or []
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    line_y, left, right = sum(ys) / len(ys), min(xs), max(xs)
    overlap = max(0.0, min(right, c["x"] + c["width"]) - max(left, c["x"]))
    under_share = overlap / max(1.0, right - left)
    gap = line_y - (c["y"] + c["height"])
    if under_share >= 0.5 and 0 <= gap <= 16:
        pos = "the stroke is drawn directly under this element, like an underline"
    elif c["y"] > line_y:
        pos = "this element is below the stroke"
    elif under_share < 0.2:
        pos = "this element is beside the stroke, not over it"
    else:
        pos = "this element is above the stroke but not directly on it"
    return {"position": pos}


def relation_numbers(c, m, is_point):
    if is_point:
        cx, cy = m["x"], m["y"]
        return {
            "point_inside": c["x"] <= cx <= c["x"] + c["width"]
            and c["y"] <= cy <= c["y"] + c["height"],
            "element_area_px": round(_area(c)),
        }
    inter = _inter(c, m)
    return {
        "fraction_of_element_inside_mark": round(inter / _area(c), 2)
        if _area(c)
        else 0,
        "fraction_of_mark_covered_by_element": round(inter / _area(m), 2)
        if _area(m)
        else 0,
        "element_area_over_mark_area": round(_area(c) / _area(m), 2)
        if _area(m)
        else None,
    }


def e1_request(case: dict, variant: str):
    ctx = from_v2(
        question=case["question"],
        marks=case["marks"],
        anchors=case["anchors"],
        canvas=case["canvas"],
        page={"surface": case["surface"]},
        privacy_policy="anchors_only",
    )
    resolution = resolve_marks(*resolver_inputs(ctx))
    first = resolution["candidates"][0] if resolution["candidates"] else {}
    ranked_ids = [item["id"] for item in first.get("anchors_ranked", [])][:8]
    if not ranked_ids:
        return None, ranked_ids, {}
    by_id = {a["id"]: a for a in case["anchors"]}
    raw_mark = resolver_inputs(ctx)[0][0]
    is_point = raw_mark["type"] == "point"
    m = {k: raw_mark.get(k, 0) for k in ("x", "y", "width", "height")}
    letters = dict(zip(LETTERS, ranked_ids))
    elements = {}
    for letter, cid in letters.items():
        box = by_id[cid]["bbox"]
        open_stroke = raw_mark["type"] == "polygon" and raw_mark.get("closed") is False
        if variant == "num":
            rel = relation_numbers(box, m, is_point)
        elif variant == "qual2" and open_stroke:
            rel = relation_stroke(box, raw_mark)
        else:
            rel = relation_words(box, m, is_point)
        others = [(l2, by_id[c2]["bbox"]) for l2, c2 in letters.items() if l2 != letter]
        element = {
            "kind": by_id[cid].get("type", "element"),
            "text": (by_id[cid].get("text") or "(no text)")[:300],
            **rel,
        }
        inside = [l2 for l2, b2 in others if _contains(b2, box)]
        contains = [l2 for l2, b2 in others if _contains(box, b2)]
        if inside:
            element["inside_elements"] = inside
        if contains:
            element["contains_elements"] = contains
        elements[letter] = element
    state = {
        "user_question": case["question"],
        "mark": mark_shape(raw_mark),
        "screen": "a PDF document" if case["surface"] == "pdf" else "a web page",
        "elements": elements,
    }
    criteria = {
        letter: f"element {letter}: {el['kind']} “{el['text'][:80]}”"
        for letter, el in elements.items()
    }
    criteria["none"] = "none of the listed elements is what the user marked"
    questions = {
        "target": {
            "type": "choice",
            "instructions": "The user marked part of the screen (`mark`) and asked `user_question`. "
            "Which one element in `elements` is the user referring to?",
            "criteria": criteria,
        },
        "ambiguous": {
            "type": "noul",
            "instructions": "Given `mark` and `user_question`, could the user reasonably be referring to "
            "two or more different elements in `elements`?",
            "criteria": {
                "true": "two or more listed elements are equally plausible targets",
                "false": "one listed element is clearly the target",
            },
        },
    }
    return (state, questions), ranked_ids, letters


def run_e1():
    cases = evaluation.load_cases(
        [ROOT / "server/tests/cases", ROOT / "server/tests/eval_cases"]
    )
    cases = [
        c for c in cases if not c.get("multi")
    ]  # multi-mark golden case: out of scope for a single Choice
    rows = []
    jobs = []
    for case in cases:
        for variant in VARIANTS:
            request, ranked, letters = e1_request(case, variant)
            jobs.append((case, variant, request, ranked, letters))

    def work(job):
        case, variant, request, ranked, letters = job
        intended = case["intended"]
        det_top = ranked[0] if ranked else None
        row = {
            "case": case["name"],
            "category": case["category"],
            "variant": variant,
            "intended": intended,
            "ambiguous_label": case["ambiguous"],
            "deterministic": det_top,
            "deterministic_ok": (det_top in intended)
            if intended != [None]
            else det_top is None,
        }
        if request is None:
            row.update(
                jev=None,
                jev_ok=intended == [None],
                confidence=None,
                p_ambiguous=None,
                latency_ms=0,
                tokens=0,
            )
            return row
        answers, usage, latency = ask(*request)
        choice = answers["target"]["choice"]
        picked = letters.get(choice)
        row.update(
            jev=picked,
            jev_ok=(picked in intended) if intended != [None] else picked is None,
            confidence=answers["target"]["confidence"],
            probabilities=answers["target"]["probabilities"],
            p_ambiguous=answers["ambiguous"]["noul"],
            latency_ms=round(latency),
            tokens=usage.get("input_tokens", 0),
        )
        return row

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(work, jobs))
    return rows


# --- E2: routing ----------------------------------------------------------------------------------------------

E2_ITEMS = [
    # (question, marked text, kind, previous question or None, mode, needs_outside_facts, visual, same_target)
    (
        "why is this step dividing by 2?",
        "dy/dx = (2x)/2 = x",
        "equation",
        None,
        "explain",
        False,
        False,
        None,
    ),
    (
        "what does this word mean?",
        "heteroscedasticity",
        "word",
        None,
        "define",
        False,
        False,
        None,
    ),
    (
        "tl;dr",
        "Batch normalization rescales activations so training stays stable. It was introduced in 2015 ...",
        "paragraph",
        None,
        "summarize",
        False,
        False,
        None,
    ),
    (
        "how is this different from that?",
        "SOURCE: Adam optimizer | TARGET: SGD with momentum",
        "two items",
        None,
        "compare",
        False,
        False,
        None,
    ),
    (
        "translate this to English",
        "La descente de gradient met à jour chaque poids",
        "sentence",
        None,
        "translate",
        False,
        False,
        None,
    ),
    (
        "why am I getting this error?",
        "TypeError: Cannot read properties of undefined (reading 'map')",
        "error message",
        None,
        "debug_error",
        False,
        False,
        None,
    ),
    (
        "what does this chart show?",
        "(no text) image of a line chart",
        "chart",
        None,
        "explain",
        False,
        True,
        None,
    ),
    (
        "who invented this?",
        "Backpropagation",
        "heading",
        None,
        "explain",
        True,
        False,
        None,
    ),
    (
        "is this claim still true in 2026?",
        "GPT-3 is the largest language model available.",
        "sentence",
        None,
        "explain",
        True,
        False,
        None,
    ),
    (
        "what is the latest version of this library?",
        "pydantic 2.7",
        "code comment",
        None,
        "other",
        True,
        False,
        None,
    ),
    (
        "explain this diagram",
        "(no text) architecture diagram with arrows",
        "diagram",
        None,
        "explain",
        False,
        True,
        None,
    ),
    (
        "what does this icon do?",
        "(no text) gear icon button",
        "icon",
        None,
        "explain",
        False,
        True,
        None,
    ),
    (
        "summarize this section",
        "Section 3: Results. We observe a 12% improvement ...",
        "section",
        None,
        "summarize",
        False,
        False,
        None,
    ),
    ("define this term", "overfitting", "word", None, "define", False, False, None),
    (
        "fix this",
        "SyntaxError: unexpected EOF while parsing",
        "error message",
        None,
        "debug_error",
        False,
        False,
        None,
    ),
    (
        "what's the difference between these two?",
        "SOURCE: TCP | TARGET: UDP",
        "two items",
        None,
        "compare",
        False,
        False,
        None,
    ),
    (
        "can you say this in Hindi?",
        "The validation loss rises when the model overfits.",
        "sentence",
        None,
        "translate",
        False,
        False,
        None,
    ),
    (
        "what's the trend here?",
        "(no text) bar chart of revenue per quarter",
        "chart",
        None,
        "explain",
        False,
        True,
        None,
    ),
    (
        "what's the current price of this?",
        "NVIDIA RTX 5090",
        "product name",
        None,
        "other",
        True,
        False,
        None,
    ),
    (
        "what does this function return?",
        "def area(r): return 3.14159 * r * r",
        "code",
        None,
        "explain",
        False,
        False,
        None,
    ),
    (
        "give me the gist",
        "Long terms-of-service paragraph about data retention for 90 days ...",
        "paragraph",
        None,
        "summarize",
        False,
        False,
        None,
    ),
    (
        "what color scheme is used in this UI?",
        "(no text) screenshot region of a settings panel",
        "ui region",
        None,
        "other",
        False,
        True,
        None,
    ),
    (
        "where was this paper published?",
        "Attention Is All You Need",
        "title",
        None,
        "other",
        True,
        False,
        None,
    ),
    (
        "what does 'p < 0.05' mean here?",
        "results were significant (p < 0.05)",
        "sentence",
        None,
        "define",
        False,
        False,
        None,
    ),
    (
        "and what about this part?",
        "the second term, −η∇L(θ)",
        "equation",
        "why is this step dividing by 2?",
        "explain",
        False,
        False,
        False,
    ),
    (
        "can you explain it more simply?",
        "dy/dx = (2x)/2 = x",
        "equation",
        "why is this step dividing by 2?",
        "explain",
        False,
        False,
        True,
    ),
    (
        "why?",
        "dy/dx = (2x)/2 = x",
        "equation",
        "what does this line compute?",
        "explain",
        False,
        False,
        True,
    ),
    (
        "what does this other button do?",
        "Export",
        "button",
        "what does this do?",
        "explain",
        False,
        False,
        False,
    ),
    (
        "give an example of it",
        "overfitting",
        "word",
        "define this term",
        "explain",
        False,
        False,
        True,
    ),
    (
        "compare it with this one",
        "SOURCE: previous figure | TARGET: Figure 3",
        "two items",
        "what does this chart show?",
        "compare",
        False,
        True,
        False,
    ),
    (
        "is this a known bug?",
        "Segmentation fault (core dumped) in libtorch 2.14",
        "error message",
        None,
        "debug_error",
        True,
        False,
        None,
    ),
    (
        "what's this?",
        "(no text) photo of a leaf",
        "image",
        None,
        "explain",
        False,
        True,
        None,
    ),
    (
        "rewrite this more formally",
        "hey guys the build is broken again lol",
        "sentence",
        None,
        "other",
        False,
        False,
        None,
    ),
    (
        "what is the capital mentioned here and its population today?",
        "Canberra hosts the parliament.",
        "sentence",
        None,
        "other",
        True,
        False,
        None,
    ),
    (
        "explain this line",
        "for i in range(len(xs)): total += xs[i]",
        "code",
        None,
        "explain",
        False,
        False,
        None,
    ),
    (
        "what does this acronym stand for?",
        "RLCD",
        "word",
        None,
        "define",
        False,
        False,
        None,
    ),
    (
        "summarize the table",
        "Q1 $1.2M, Q2 $1.5M, Q3 $0.9M, Q4 $2.1M",
        "table",
        None,
        "summarize",
        False,
        False,
        None,
    ),
    (
        "why does this layout look broken?",
        "(no text) region of a web page with overlapping boxes",
        "ui region",
        None,
        "debug_error",
        False,
        True,
        None,
    ),
    (
        "what does the legend say?",
        "(no text) chart legend area",
        "chart",
        None,
        "explain",
        False,
        True,
        None,
    ),
    (
        "translate these labels",
        "Umsatz, Gewinn, Verlust",
        "labels",
        None,
        "translate",
        False,
        False,
        None,
    ),
]
MODES = {
    "explain": "explain how or why the marked thing works or what it shows",
    "define": "give the meaning of a word, term, symbol or acronym",
    "summarize": "shorten a longer marked passage, table or section",
    "compare": "compare two marked things or contrast one with another",
    "translate": "translate the marked text into another language",
    "debug_error": "diagnose an error message, bug or broken layout and how to fix it",
    "other": "anything else (rewrite, facts about the thing, prices, publication details, styling)",
}


def run_e2():
    def work(item):
        question, text, kind, prev, mode, facts, visual, same = item
        state = {"user_question": question, "marked": {"kind": kind, "text": text}}
        if prev:
            state["previous_question_in_this_conversation"] = prev
        questions = {
            "mode": {
                "type": "choice",
                "instructions": "What kind of help does the user want for the marked thing?",
                "criteria": MODES,
            },
            "needs_outside_facts": {
                "type": "noul",
                "instructions": "Does answering `user_question` well require facts "
                "that are not in `marked` and may be current or specific (dates, people, prices, "
                "versions, whether a claim is still true)?",
            },
            "visual": {
                "type": "noul",
                "instructions": "Is the marked thing mainly visual (a chart, diagram, image, icon "
                "or UI layout) so that the answer needs to see it rather than read its text?",
            },
        }
        if prev:
            questions["same_target"] = {
                "type": "noul",
                "instructions": "Is `user_question` about the same marked "
                "thing as `previous_question_in_this_conversation`, rather than a new thing?",
            }
        answers, usage, latency = ask(state, questions)
        row = {
            "question": question,
            "mode": mode,
            "mode_pred": answers["mode"]["choice"],
            "mode_conf": answers["mode"]["confidence"],
            "facts": facts,
            "p_facts": answers["needs_outside_facts"]["noul"],
            "visual": visual,
            "p_visual": answers["visual"]["noul"],
            "latency_ms": round(latency),
            "tokens": usage.get("input_tokens", 0),
        }
        if prev:
            row.update(same=same, p_same=answers["same_target"]["noul"])
        return row

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(work, E2_ITEMS))


def main():
    if not KEY:
        sys.exit("TYPESAFE_API_KEY missing (server/.env)")
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT.mkdir(exist_ok=True)
    if which in {"e1", "all"}:
        rows = run_e1()
        (OUT / os.environ.get("E1_OUT", "e1_target.json")).write_text(
            json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        print(f"E1 rows: {len(rows)}")
    if which in {"e2", "all"}:
        rows = run_e2()
        (OUT / "e2_routing.json").write_text(
            json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        print(f"E2 rows: {len(rows)}")


if __name__ == "__main__":
    main()
