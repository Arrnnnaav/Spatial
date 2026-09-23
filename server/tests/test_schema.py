import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.contracts import schema_document  # noqa: E402

SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "spatial-context.v3.json"


def test_committed_schema_matches_models():
    assert SCHEMA.exists(), "run: python scripts/export_schema.py"
    assert json.loads(SCHEMA.read_text(encoding="utf-8")) == schema_document()


def test_schema_covers_contract():
    defs = schema_document()["$defs"]
    assert {
        "SpatialContext",
        "CandidateObject",
        "SpatialMark",
        "SemanticResolution",
    } <= set(defs)
    assert defs["CandidateObject"]["properties"]["source"]["enum"] == [
        "dom",
        "pdf_text",
        "ocr",
        "uia",
        "vision",
    ]
