"""Golden resolver cases (tests/cases/*.json).
Runs each case through app.resolver.resolve_marks and, when node is available, through
extension/geometry.js to prove client and server rank anchors identically."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.resolver import resolve_marks  # noqa: E402

CASES = sorted((Path(__file__).parent / "cases").glob("*.json"))
EVAL_CASES = sorted((Path(__file__).parent / "eval_cases").glob("*.json"))
GEOMETRY = ROOT.parent / "extension" / "geometry.js"
NODE = shutil.which("node")

JS_RUNNER = """
const G = require(process.argv[1]); const kase = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const out = [];
for (const raw of kase.marks) {
  const mark = raw.type === 'polygon' && raw.x === undefined ? G.strokeToMark(raw.points, raw.role) : { ...raw, width: raw.width || 0, height: raw.height || 0 };
  const ranked = G.rankAnchors(kase.anchors, mark).map(a => a.id);
  out.push({ role: mark.role, bbox: { x: mark.x, y: mark.y, width: mark.width, height: mark.height }, top: ranked[0] || null, ranked });
}
process.stdout.write(JSON.stringify(out));
"""


def python_resolution(case: dict) -> list[dict]:
    resolution = resolve_marks(case["marks"], case["canvas"], case["anchors"])
    return [
        {
            "role": c["role"],
            "bbox": {k: m.get(k, 0) for k in ("x", "y", "width", "height")},
            "top": c.get("anchor_id"),
            "ranked": [item["id"] for item in c.get("anchors_ranked", [])],
        }
        for m, c in zip(resolution["normalized_marks"], resolution["candidates"])
    ]


@pytest.mark.parametrize("case_path", CASES, ids=[p.stem for p in CASES])
def test_python_matches_expectation(case_path: Path):
    case = json.loads(case_path.read_text(encoding="utf-8"))
    expect = case["expect"]
    marks = python_resolution(case)
    if "tops" in expect:
        assert [m["top"] for m in marks] == expect["tops"] and [
            m["role"] for m in marks
        ] == expect["roles"]
    else:
        assert (
            marks[0]["top"] == expect["top"] and marks[0]["ranked"] == expect["ranked"]
        )
    if "bbox" in expect:
        assert marks[0]["bbox"] == expect["bbox"]


@pytest.mark.skipif(
    NODE is None or not GEOMETRY.exists(),
    reason="node or extension/geometry.js missing",
)
@pytest.mark.parametrize("case_path", CASES + EVAL_CASES, ids=[p.stem for p in CASES + EVAL_CASES])
def test_js_matches_python(case_path: Path):
    case = json.loads(case_path.read_text(encoding="utf-8"))
    js = json.loads(
        subprocess.run(
            [NODE, "-e", JS_RUNNER, str(GEOMETRY), str(case_path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    for p, j in zip(python_resolution(case), js):
        assert j["top"] == p["top"] and j["ranked"] == p["ranked"]
        assert {k: round(float(v), 2) for k, v in j["bbox"].items()} == {
            k: round(float(v), 2) for k, v in p["bbox"].items()
        }
