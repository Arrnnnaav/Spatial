import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import pytest  # noqa: E402

from app import evaluation  # noqa: E402

TESTS = Path(__file__).parent
DIRS = [TESTS / "cases", TESTS / "eval_cases"]


def test_cases_load_and_normalize():
    cases = evaluation.load_cases(DIRS)
    assert len(cases) >= 50
    cats = {c["category"] for c in cases}
    assert {"web", "pdf", "ambiguous", "ocr", "golden"} <= cats
    assert all(c["intended"] for c in cases)


def test_run_case_scores_top1_and_top3():
    case = {
        "name": "t",
        "category": "web",
        "question": "q",
        "surface": "web",
        "canvas": {"width": 1280, "height": 720},
        "marks": [
            {
                "type": "rectangle",
                "role": "reference",
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 60,
            }
        ],
        "anchors": [
            {
                "id": "hit",
                "type": "p",
                "text": "hit",
                "bbox": {"x": 100, "y": 100, "width": 200, "height": 60},
            },
            {
                "id": "near",
                "type": "p",
                "text": "near",
                "bbox": {"x": 100, "y": 150, "width": 200, "height": 60},
            },
        ],
        "intended": ["near"],
        "ambiguous": False,
    }
    result = evaluation.run_case(case)
    assert (
        result["predicted"] == ["hit"]
        and result["top1"] is False
        and result["top3"] is True
    )


def test_expected_no_match_counts_an_empty_ranking_as_correct():
    case = {
        "name": "none",
        "category": "golden",
        "question": "q",
        "surface": "web",
        "canvas": {"width": 1280, "height": 720},
        "marks": [
            {
                "type": "rectangle",
                "role": "reference",
                "x": 900,
                "y": 600,
                "width": 50,
                "height": 50,
            }
        ],
        "anchors": [
            {
                "id": "far",
                "type": "p",
                "text": "far",
                "bbox": {"x": 0, "y": 0, "width": 50, "height": 50},
            }
        ],
        "intended": [None],
        "ambiguous": False,
    }
    result = evaluation.run_case(case)
    assert (
        result["predicted"] == [] and result["top1"] is True and result["top3"] is True
    )


def test_summary_metrics_shape():
    summary = evaluation.summarize(
        [evaluation.run_case(c) for c in evaluation.load_cases(DIRS)]
    )
    assert {
        "cases",
        "top1",
        "top3",
        "abstain_rate",
        "p50_ms",
        "p95_ms",
        "by_category",
    } <= set(summary)
    assert 0.0 <= summary["top1"] <= summary["top3"] <= 1.0


def test_no_regression_against_committed_baseline():
    baseline = json.loads((TESTS / "eval_baseline.json").read_text(encoding="utf-8"))
    summary = evaluation.summarize(
        [evaluation.run_case(c) for c in evaluation.load_cases(DIRS)]
    )
    assert summary["top1"] >= baseline["top1"] - 0.02


def test_trace_replay(tmp_path):
    record = {
        "question": "What is this?",
        "privacy_policy": "crop_only",
        "surface": {
            "kind": "web",
            "url": "",
            "title": "",
            "viewport": {"width": 1280, "height": 720},
        },
        "marks": [
            {
                "kind": "rectangle",
                "role": "reference",
                "bbox": {"x": 100, "y": 100, "width": 200, "height": 60},
            }
        ],
        "candidates": [
            {
                "candidate_id": "hit",
                "source": "dom",
                "text": "hit",
                "provenance": {"extractor": "t"},
                "bbox": {"x": 100, "y": 100, "width": 200, "height": 60},
            }
        ],
        "resolution": {"selected_candidate_id": "hit"},
    }
    (tmp_path / "2026-09-23.jsonl").write_text(
        json.dumps(record) + "\n{not json\n", encoding="utf-8"
    )
    records = evaluation.load_traces(tmp_path)
    assert len(records) == 1
    assert evaluation.run_trace(records[0])["top1"] is True


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
