import os
import sys
from pathlib import Path

os.environ.setdefault("SPATIAL_DB", str(Path(__file__).parent / "test_spatial.db"))
os.environ.setdefault("SPATIAL_PROVIDERS", "nothing")
os.environ.setdefault("SPATIAL_OCR", "0")
os.environ.setdefault("SPATIAL_API_TOKEN", "")
sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import candidates, main  # noqa: E402
from app.contracts import BBox, CandidateObject, CropInfo, Provenance  # noqa: E402
from tests.test_server import PAYLOAD  # noqa: E402

BLOCKS = [
    {
        "text": "Revenue by quarter",
        "bbox": {"x": 20, "y": 10, "width": 200, "height": 30},
        "confidence": 0.93,
    },
    {
        "text": "Pectoralis major",
        "bbox": {"x": 40, "y": 60, "width": 160, "height": 20},
        "confidence": 0.9,
    },
]


def cand(cid, source, text, x, y, w, h):
    return CandidateObject(
        candidate_id=cid,
        source=source,
        text=text,
        bbox=BBox(x=x, y=y, width=w, height=h),
        provenance=Provenance(extractor="t"),
    )


def test_ocr_boxes_map_from_crop_to_surface_coordinates():
    crop = CropInfo(bbox=BBox(x=100, y=50, width=400, height=200), scale=2.0)
    out = candidates.ocr_candidates(BLOCKS, crop)
    assert [c.candidate_id for c in out] == ["ocr-0", "ocr-1"]
    assert out[0].source == "ocr" and out[0].bbox == BBox(
        x=110, y=55, width=100, height=15
    )
    assert out[0].attributes["confidence"] == "0.93"


def test_no_crop_means_no_ocr_candidates():
    assert candidates.ocr_candidates(BLOCKS, None) == []


def test_ocr_ids_do_not_replace_client_candidate_ids():
    crop = CropInfo(bbox=BBox(x=0, y=0, width=400, height=200), scale=1.0)
    out = candidates.ocr_candidates(BLOCKS, crop, existing_ids={"ocr-0", "ocr-1"})
    assert [c.candidate_id for c in out] == ["ocr-2", "ocr-3"]


def test_merge_drops_ocr_duplicating_structured_text_and_keeps_unique():
    dom = cand("a1", "dom", "The Pectoralis major muscle", 100, 100, 300, 60)
    dup = cand(
        "ocr-1", "ocr", "pectoralis  MAJOR", 120, 110, 150, 20
    )  # inside a1, text contained
    unique = cand("ocr-0", "ocr", "Revenue by quarter", 600, 100, 200, 30)
    far_dup_text = cand(
        "ocr-2", "ocr", "Pectoralis major", 900, 600, 150, 20
    )  # same words, elsewhere: keep
    merged = candidates.merge([dom, dup, unique, far_dup_text])
    assert [c.candidate_id for c in merged] == ["a1", "ocr-0", "ocr-2"]


def test_merge_caps_candidates():
    many = [cand(f"c{i}", "dom", f"t{i}", i, 0, 1, 1) for i in range(100)]
    assert len(candidates.merge(many)) == 64


def test_ask_uses_ocr_candidates_when_crop_given(monkeypatch):
    monkeypatch.setattr(main.settings, "ocr_enabled", True)
    monkeypatch.setattr(main, "ocr_blocks", lambda image: BLOCKS)
    body = {
        **PAYLOAD,
        "anchors": [],
        "image_data": "data:image/jpeg;base64,AAAA",
        "crop": {"bbox": {"x": 80, "y": 80, "width": 260, "height": 140}, "scale": 1.0},
    }
    with TestClient(main.app) as client:
        result = client.post("/api/ask", json=body).json()
    assert result["anchors_used"][0]["id"].startswith("ocr-")
    assert result["anchors_used"][0]["type"] == "ocr"


def test_ask_skips_unplaced_ocr_when_candidate_text_exists(monkeypatch):
    monkeypatch.setattr(main.settings, "ocr_enabled", True)
    calls = []
    monkeypatch.setattr(main, "ocr_blocks", lambda image: calls.append(image) or BLOCKS)
    body = {**PAYLOAD, "image_data": "data:image/jpeg;base64,AAAA"}
    with TestClient(main.app) as client:
        assert client.post("/api/ask", json=body).status_code == 200
    assert calls == []


def test_ask_keeps_unplaced_ocr_for_text_fallback(monkeypatch):
    monkeypatch.setattr(main.settings, "ocr_enabled", True)
    calls = []
    monkeypatch.setattr(main, "ocr_blocks", lambda image: calls.append(image) or BLOCKS)
    body = {**PAYLOAD, "anchors": [], "image_data": "data:image/jpeg;base64,AAAA"}
    with TestClient(main.app) as client:
        assert client.post("/api/ask", json=body).status_code == 200
    assert len(calls) == 1
