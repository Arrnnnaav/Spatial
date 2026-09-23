import os
import sys
from pathlib import Path

os.environ.setdefault("SPATIAL_DB", str(Path(__file__).parent / "test_spatial.db"))
os.environ.setdefault("SPATIAL_PROVIDERS", "nothing")
os.environ.setdefault("SPATIAL_OCR", "0")
os.environ.setdefault("SPATIAL_API_TOKEN", "")
sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from tests.test_server import PAYLOAD  # noqa: E402

V3 = {
    "protocol_version": 3,
    "context": {
        "surface": {
            "kind": "web",
            "url": "https://example.org/anatomy",
            "title": "Anatomy atlas",
            "viewport": {"width": 1280, "height": 720},
        },
        "marks": [
            {
                "kind": "polygon",
                "role": "reference",
                "bbox": {"x": 100, "y": 100, "width": 200, "height": 100},
                "points": [[100, 100], [300, 100], [300, 200], [100, 200]],
            }
        ],
        "candidates": [
            {
                "candidate_id": "a1",
                "source": "dom",
                "object_type": "img",
                "text": "Pectoralis major",
                "bbox": {"x": 90, "y": 90, "width": 220, "height": 120},
                "provenance": {"extractor": "test"},
            },
            {
                "candidate_id": "a2",
                "source": "dom",
                "object_type": "p",
                "text": "Unrelated footer",
                "bbox": {"x": 0, "y": 600, "width": 500, "height": 40},
                "provenance": {"extractor": "test"},
            },
        ],
        "question": "What is this?",
    },
}


def test_v2_and_v3_resolve_the_same():
    with TestClient(app) as client:
        a = client.post("/api/ask", json=PAYLOAD).json()
        b = client.post("/api/ask", json=V3).json()
    assert a["anchors_used"][0]["id"] == b["anchors_used"][0]["id"] == "a1"
    assert a["confidence"] == b["confidence"]
    assert (
        a["resolution_v3"]["selected_candidate_id"]
        == b["resolution_v3"]["selected_candidate_id"]
        == "a1"
    )
    assert b["page"] == {
        "url": "https://example.org/anatomy",
        "title": "Anatomy atlas",
        "surface": "web",
    }
    assert b["protocol_version"] == 3


def test_v3_without_context_is_rejected():
    with TestClient(app) as client:
        r = client.post("/api/ask", json={"protocol_version": 3})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_CONTEXT"


def test_v3_invalid_context_uses_error_shape():
    bad = {"protocol_version": 3, "context": {**V3["context"], "marks": []}}
    with TestClient(app) as client:
        r = client.post("/api/ask", json=bad)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_CONTEXT"


def test_v2_without_question_is_rejected():
    body = {k: v for k, v in PAYLOAD.items() if k != "question"}
    with TestClient(app) as client:
        r = client.post("/api/ask", json=body)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_CONTEXT"


def test_v2_with_only_unusable_marks_is_no_marks():
    with TestClient(app) as client:
        r = client.post("/api/ask", json={**PAYLOAD, "marks": [{"type": "scribble"}]})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "NO_MARKS"


def test_unknown_privacy_policy_drops_image():
    with TestClient(app) as client:
        body = client.post(
            "/api/ask",
            json={
                **PAYLOAD,
                "privacy_policy": "weird",
                "image_data": "data:image/jpeg;base64,AAAA",
            },
        ).json()
    assert body["resolution"]["image_attached"] is False
