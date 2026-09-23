"""Deterministic mark resolver: normalizes marks, derives bounding boxes for freehand strokes,
and ranks the DOM/PDF anchors under each mark. Runs before any model call and explains its confidence.
Ranking must stay identical to extension/geometry.js::rankAnchors (see tests/test_resolver_cases.py)."""
from __future__ import annotations

from time import perf_counter


def resolve_marks(marks: list[dict], canvas: dict | None = None, anchors: list[dict] | None = None) -> dict:
    """Cheap deterministic resolver used before any VLM call; returns explainable confidence."""
    started = perf_counter()
    candidates = []
    normalized = []
    valid_anchors = []
    for anchor in anchors or []:
        if not isinstance(anchor, dict) or not anchor.get("id"):
            continue
        bbox = anchor.get("bbox") or anchor.get("rect")
        if not isinstance(bbox, dict):
            continue
        try:
            valid_anchors.append({"id": str(anchor["id"]), "type": str(anchor.get("type", "unknown")),
                                  "text": str(anchor.get("text") or "")[:1200], "page": anchor.get("page"),
                                  "x": float(bbox.get("x", 0)), "y": float(bbox.get("y", 0)),
                                  "width": max(0.0, float(bbox.get("width", 0))), "height": max(0.0, float(bbox.get("height", 0)))})
        except (TypeError, ValueError):
            continue
    canvas_width = max(float((canvas or {}).get("width", 1)), 1.0)
    canvas_height = max(float((canvas or {}).get("height", 1)), 1.0)
    for index, mark in enumerate(marks):
        kind = mark.get("type", "unknown")
        if kind not in {"point", "rectangle", "circle", "polygon", "arrow", "line"}:
            continue
        clean = dict(mark)
        try:
            points = clean.get("points")
            if kind in {"polygon", "line", "arrow"} and isinstance(points, list) and points:
                # Freehand strokes arrive as point lists. The client's bbox (which pads open strokes) is the
                # contract; only derive one from the points when the client sent none.
                xs = [float(point[0]) for point in points]; ys = [float(point[1]) for point in points]
                clean["points"] = [[round(x, 2), round(y, 2)] for x, y in zip(xs, ys)][:2000]
                if not all(axis in clean for axis in ("x", "y", "width", "height")):
                    clean.update({"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)})
            for axis in ("x", "y", "width", "height"):
                if axis in clean:
                    clean[axis] = max(0.0, float(clean[axis]))
            if kind in {"point", "rectangle", "circle", "arrow", "line"}:
                if "x" in clean: clean["x_norm"] = round(min(clean["x"] / canvas_width, 1.0), 6)
                if "y" in clean: clean["y_norm"] = round(min(clean["y"] / canvas_height, 1.0), 6)
                if "width" in clean: clean["width_norm"] = round(min(clean["width"] / canvas_width, 1.0), 6)
                if "height" in clean: clean["height_norm"] = round(min(clean["height"] / canvas_height, 1.0), 6)
        except (TypeError, ValueError):
            continue
        normalized.append(clean)
        candidate = {"mark_index": index, "kind": kind, "role": mark.get("role", "reference")}
        if valid_anchors and "x" in clean and "y" in clean:
            mark_width = max(0.0, clean.get("width", 0))
            mark_height = max(0.0, clean.get("height", 0))
            mark_right = clean["x"] + mark_width
            mark_bottom = clean["y"] + mark_height
            scored = []
            for anchor in valid_anchors:
                right = anchor["x"] + anchor["width"]
                bottom = anchor["y"] + anchor["height"]
                intersection = max(0.0, min(mark_right, right) - max(clean["x"], anchor["x"])) * max(0.0, min(mark_bottom, bottom) - max(clean["y"], anchor["y"]))
                mark_area = mark_width * mark_height
                anchor_area = anchor["width"] * anchor["height"]
                union = mark_area + anchor_area - intersection
                iou = intersection / union if union else 0.0
                mark_overlap = intersection / mark_area if mark_area else 0.0
                anchor_overlap = intersection / anchor_area if anchor_area else 0.0
                center_x = clean["x"] + mark_width / 2
                center_y = clean["y"] + mark_height / 2
                contains_center = anchor["x"] <= center_x <= right and anchor["y"] <= center_y <= bottom
                contains_anchor = clean["x"] <= anchor["x"] and clean["y"] <= anchor["y"] and mark_right >= right and mark_bottom >= bottom
                score = max(iou, min(0.94, mark_overlap * 0.9), min(0.95, anchor_overlap * 0.95), 0.95 if contains_center and not mark_area else 0.0, 0.96 if contains_anchor else 0.0)
                if score >= 0.10:
                    match_type = "contains_anchor" if contains_anchor else ("contains_center" if contains_center and not mark_area else "overlap_ranked")
                    scored.append((score, anchor, match_type))
            if scored:
                # Ranking rule shared with extension/geometry.js (golden cases in tests/cases): score desc,
                # then more text (more specific), then smaller area.
                ranked = sorted(scored, key=lambda item: (-round(item[0], 6), -len(item[1]["text"]), item[1]["width"] * item[1]["height"]))
                score, anchor, match = ranked[0]
                candidate.update({"anchor_id": anchor["id"], "anchor_type": anchor["type"], "anchor_match": match, "anchor_overlap": round(score, 3),
                                  "anchor_text": anchor["text"][:200], "anchor_page": anchor["page"],
                                  "anchors_ranked": [{"id": item[1]["id"], "type": item[1]["type"], "score": round(item[0], 3), "text": item[1]["text"], "page": item[1]["page"]}
                                                     for item in ranked[:8]]})
        candidates.append(candidate)
    confidence = 0.78 if candidates else 0.0
    matched = sum("anchor_id" in candidate for candidate in candidates)
    if valid_anchors and candidates:
        confidence = min(0.99, confidence + 0.18 * matched / len(candidates))
        if not matched:
            confidence = min(confidence, 0.72)
    roles = {item["role"] for item in candidates}
    if "source" in roles and "target" in roles:
        confidence = min(0.97, confidence + 0.03)
    if canvas and any("width" in item and "height" in item and (item["width"] == 0 or item["height"] == 0) for item in normalized):
        confidence = min(confidence, 0.65)
    return {"candidates": candidates, "normalized_marks": normalized, "anchors_considered": len(valid_anchors),
            "canvas": {"width": canvas_width, "height": canvas_height}, "confidence": confidence,
            "resolver": "structured-anchor-v1" if valid_anchors else "deterministic-v1", "latency_ms": round((perf_counter()-started)*1000),
            "next": "plugin/dom/uia resolver" if canvas else "crop-or-document resolver"}
