import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.contracts import (
    CropInfo,
    SpatialContext,
    candidate_to_anchor,
    from_v2,
    mark_to_v2,  # noqa: E402
    page_dict,
    resolver_inputs,
    to_semantic_resolution,
)
from app.resolver import resolve_marks  # noqa: E402

PAGE = {"url": "https://example.org", "title": "Example", "surface": "web"}
ANCHORS = [
    {
        "id": "a1",
        "type": "p",
        "text": "Pectoralis major",
        "bbox": {"x": 90, "y": 90, "width": 220, "height": 120},
    },
    {
        "id": "a2",
        "type": "p",
        "text": "Footer",
        "bbox": {"x": 0, "y": 600, "width": 500, "height": 40},
    },
]


def v2(marks, anchors=ANCHORS, page=PAGE, privacy="crop_only"):
    return from_v2(
        question="What is this?",
        marks=marks,
        anchors=anchors,
        canvas={"width": 1280, "height": 720},
        page=page,
        privacy_policy=privacy,
    )


def test_rectangle_and_dom_anchor_convert():
    ctx = v2(
        [
            {
                "type": "rectangle",
                "role": "source",
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 100,
            }
        ]
    )
    assert ctx.marks[0].kind == "rectangle" and ctx.marks[0].role == "source"
    assert ctx.marks[0].bbox.width == 200
    assert [c.source for c in ctx.candidates] == ["dom", "dom"]
    assert (
        ctx.candidates[0].candidate_id == "a1" and ctx.candidates[0].object_type == "p"
    )
    assert ctx.surface.viewport.width == 1280 and ctx.surface.kind == "web"


def test_pdf_surface_and_page_anchor_become_pdf_text():
    anchors = [
        {
            "id": "p",
            "type": "pdf-text",
            "page": 2,
            "text": "Abstract",
            "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
        }
    ]
    ctx = v2(
        [{"type": "circle", "x": 0, "y": 0, "width": 10, "height": 10}],
        anchors=anchors,
        page={**PAGE, "surface": "pdf"},
    )
    assert (
        ctx.surface.kind == "pdf"
        and ctx.candidates[0].source == "pdf_text"
        and ctx.candidates[0].page == 2
    )


def test_polygon_without_bbox_derives_it_from_points():
    ctx = v2(
        [{"type": "polygon", "points": [[10, 20], [110, 20], [110, 80], [10, 80]]}]
    )
    box = ctx.marks[0].bbox
    assert (box.x, box.y, box.width, box.height) == (10, 20, 100, 60)
    assert ctx.marks[0].points[0] == (10, 20)


def test_unknown_marks_and_bad_anchors_are_dropped():
    ctx = v2(
        [{"type": "scribble", "x": 1, "y": 1}, {"type": "point", "x": 5, "y": 5}],
        anchors=[
            {"id": "x"},
            {"type": "p", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}},
            *ANCHORS,
        ],
    )
    assert [m.kind for m in ctx.marks] == ["point"]
    assert [c.candidate_id for c in ctx.candidates] == ["a1", "a2"]
    with pytest.raises(ValueError):
        v2([{"type": "scribble"}])


def test_negative_anchor_coordinates_are_accepted():
    ctx = v2(
        [{"type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50}],
        anchors=[
            {
                "id": "off",
                "type": "div",
                "text": "t",
                "bbox": {"x": -40, "y": -10, "width": 100, "height": 30},
            }
        ],
    )
    assert ctx.candidates[0].bbox.x == -40


def test_unknown_privacy_policy_fails_safe():
    assert (
        v2([{"type": "point", "x": 1, "y": 1}], privacy="whatever").privacy_policy
        == "anchors_only"
    )


def test_point_mark_without_size_resolves_like_v2():
    raw = [{"type": "point", "role": "reference", "x": 150, "y": 150}]
    ctx = v2(raw)
    marks, canvas, anchors = resolver_inputs(ctx)
    assert "width" not in marks[0] and "height" not in marks[0]
    assert (
        resolve_marks(marks, canvas, anchors)["confidence"]
        == resolve_marks(raw, {"width": 1280, "height": 720}, ANCHORS)["confidence"]
    )


def test_resolver_adapter_matches_direct_v2_resolution():
    raw = [
        {
            "type": "rectangle",
            "role": "reference",
            "x": 100,
            "y": 100,
            "width": 200,
            "height": 100,
        }
    ]
    direct = resolve_marks(raw, {"width": 1280, "height": 720}, ANCHORS)
    via = resolve_marks(*resolver_inputs(v2(raw)))
    assert (
        via["candidates"][0]["anchors_ranked"]
        == direct["candidates"][0]["anchors_ranked"]
    )
    assert via["confidence"] == direct["confidence"]


def test_candidate_to_anchor_and_mark_round_trip():
    ctx = v2(
        [
            {
                "type": "polygon",
                "role": "target",
                "closed": True,
                "points": [[0, 0], [10, 0], [10, 10]],
                "x": 0,
                "y": 0,
                "width": 10,
                "height": 10,
            }
        ]
    )
    assert mark_to_v2(ctx.marks[0]) == {
        "type": "polygon",
        "role": "target",
        "x": 0.0,
        "y": 0.0,
        "width": 10.0,
        "height": 10.0,
        "points": [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]],
        "closed": True,
    }
    anchor = candidate_to_anchor(ctx.candidates[0])
    assert anchor["id"] == "a1" and anchor["bbox"] == {
        "x": 90.0,
        "y": 90.0,
        "width": 220.0,
        "height": 120.0,
    }
    assert anchor["source"] == "dom"
    assert page_dict(ctx) == {
        "url": "https://example.org",
        "title": "Example",
        "surface": "web",
    }


def test_semantic_resolution_from_resolver_output():
    res = to_semantic_resolution(
        resolve_marks(
            *resolver_inputs(
                v2(
                    [
                        {
                            "type": "rectangle",
                            "x": 100,
                            "y": 100,
                            "width": 200,
                            "height": 100,
                        }
                    ]
                )
            )
        )
    )
    assert (
        res.selected_candidate_id == "a1" and res.alternatives[0].candidate_id == "a1"
    )
    assert res.semantic_confidence is None and res.abstained is False
    assert res.resolver == "structured-anchor-v1"


def test_v3_context_validation():
    ok = SpatialContext.model_validate(
        {
            "surface": {
                "kind": "desktop",
                "app": "Code",
                "viewport": {"width": 1920, "height": 1080},
            },
            "marks": [
                {"kind": "rectangle", "bbox": {"x": 1, "y": 1, "width": 5, "height": 5}}
            ],
            "candidates": [
                {
                    "candidate_id": "u1",
                    "source": "uia",
                    "text": "Run",
                    "bbox": {"x": 0, "y": 0, "width": 9, "height": 9},
                    "provenance": {"extractor": "uia"},
                }
            ],
            "question": "what does this do?",
            "crop": {"bbox": {"x": 0, "y": 0, "width": 100, "height": 50}, "scale": 2},
        }
    )
    assert ok.candidates[0].source == "uia" and isinstance(ok.crop, CropInfo)
    with pytest.raises(ValidationError):
        SpatialContext.model_validate(
            {
                "surface": {"viewport": {"width": 1, "height": 1}},
                "marks": [],
                "question": "x",
            }
        )
