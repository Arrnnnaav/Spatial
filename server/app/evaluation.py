"""Resolver evaluation over labelled cases and recorded traces. Metrics: top-1 / top-3 accuracy against the
intended candidate(s), abstain rate (confidence < 0.6), resolver latency. Uses the same contract adapter as the
server so the numbers describe what /api/ask actually does."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from app.contracts import SpatialContext, from_v2, resolver_inputs
from app.resolver import resolve_marks


def _normalize(raw: dict, name: str) -> dict:
    if "intended" in raw:
        intended, category = raw["intended"], raw.get("category", "uncategorized")
    else:  # golden regression case: expectation doubles as the intended target
        expect = raw["expect"]
        intended, category = (
            (expect["tops"] if "tops" in expect else [expect["top"]]),
            "golden",
        )
    return {
        "name": name,
        "category": category,
        "question": raw.get("question", "what is this?"),
        "surface": raw.get("surface", "web"),
        "canvas": raw["canvas"],
        "marks": raw["marks"],
        "anchors": raw["anchors"],
        "intended": intended,
        "ambiguous": bool(raw.get("ambiguous")),
        "multi": "expect" in raw and "tops" in raw["expect"],
    }


def load_cases(dirs: list[Path]) -> list[dict]:
    cases = []
    for directory in dirs:
        for path in sorted(Path(directory).glob("*.json")):
            cases.append(
                _normalize(json.loads(path.read_text(encoding="utf-8")), path.stem)
            )
    return cases


def _score(ctx: SpatialContext, intended: list, multi: bool) -> dict:
    started = perf_counter()
    resolution = resolve_marks(*resolver_inputs(ctx))
    latency = (perf_counter() - started) * 1000
    per_mark = [
        [item["id"] for item in c.get("anchors_ranked", [])]
        for c in resolution["candidates"]
    ]
    if multi:
        tops = [ranked[0] if ranked else None for ranked in per_mark]
        top1 = top3 = tops == intended
        predicted = tops
    else:
        ranked = per_mark[0] if per_mark else []
        if intended == [None]:  # the case expects nothing under the mark
            top1 = top3 = not ranked
        else:
            top1 = bool(ranked) and ranked[0] in intended
            top3 = any(item in intended for item in ranked[:3])
        predicted = ranked[:1]
    return {
        "top1": top1,
        "top3": top3,
        "abstained": resolution["confidence"] < 0.6,
        "latency_ms": latency,
        "predicted": predicted,
        "confidence": resolution["confidence"],
    }


def run_case(case: dict) -> dict:
    ctx = from_v2(
        question=case["question"],
        marks=case["marks"],
        anchors=case["anchors"],
        canvas=case["canvas"],
        page={"surface": case["surface"]},
        privacy_policy="anchors_only",
    )
    return {
        "name": case["name"],
        "category": case["category"],
        **_score(ctx, case["intended"], case.get("multi", False)),
    }


def load_traces(directory: Path) -> list[dict]:
    records = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


def run_trace(record: dict) -> dict:
    """Replay a trace. Expected = a hand-added `label` (candidate id) if present, else what was resolved then."""
    ctx = SpatialContext.model_validate(
        {
            k: record[k]
            for k in ("surface", "marks", "candidates", "question", "privacy_policy")
        }
    )
    expected = record.get("label") or (record.get("resolution") or {}).get(
        "selected_candidate_id"
    )
    return {
        "name": record.get("request_id", "trace"),
        "category": "trace",
        **_score(ctx, [expected], False),
    }


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return (
        ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]
        if ordered
        else 0.0
    )


def summarize(results: list[dict]) -> dict[str, Any]:
    def block(items: list[dict]) -> dict[str, Any]:
        n = len(items) or 1
        return {
            "cases": len(items),
            "top1": round(sum(r["top1"] for r in items) / n, 4),
            "top3": round(sum(r["top3"] for r in items) / n, 4),
            "abstain_rate": round(sum(r["abstained"] for r in items) / n, 4),
        }

    latencies = [r["latency_ms"] for r in results]
    categories = sorted({r["category"] for r in results})
    return {
        **block(results),
        "p50_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_ms": round(_percentile(latencies, 0.95), 3),
        "by_category": {
            c: block([r for r in results if r["category"] == c]) for c in categories
        },
        "failures": [r["name"] for r in results if not r["top1"]],
    }
