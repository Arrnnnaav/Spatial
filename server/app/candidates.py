"""Candidate sources beyond what the client collected: OCR blocks from the attached crop, merged with
structured candidates (DOM / PDF text / UIA win over OCR when they describe the same thing)."""

from __future__ import annotations

from app.contracts import BBox, CandidateObject, CropInfo, Provenance

STRUCTURED = {"dom", "pdf_text", "uia"}
MAX_CANDIDATES = 64


def ocr_candidates(blocks: list[dict], crop: CropInfo | None, existing_ids: set[str] | None = None) -> list[CandidateObject]:
    """Map OCR boxes from crop px to surface px. Without crop geometry the boxes cannot be placed: no candidates."""
    if crop is None:
        return []
    out = []
    used = set(existing_ids or ())
    index = 0
    for block in blocks:
        while f"ocr-{index}" in used:
            index += 1
        candidate_id = f"ocr-{index}"
        used.add(candidate_id)
        index += 1
        box, scale = block["bbox"], crop.scale
        out.append(
            CandidateObject(
                candidate_id=candidate_id,
                source="ocr",
                object_type="ocr",
                text=str(block["text"])[:1500],
                bbox=BBox(
                    x=crop.bbox.x + box["x"] / scale,
                    y=crop.bbox.y + box["y"] / scale,
                    width=box["width"] / scale,
                    height=box["height"] / scale,
                ),
                attributes={"confidence": str(block.get("confidence", ""))},
                provenance=Provenance(extractor="rapidocr", extractor_version="1"),
            )
        )
    return out


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _inside_fraction(inner: BBox, outer: BBox) -> float:
    w = min(inner.x + inner.width, outer.x + outer.width) - max(inner.x, outer.x)
    h = min(inner.y + inner.height, outer.y + outer.height) - max(inner.y, outer.y)
    area = inner.width * inner.height
    return (w * h) / area if w > 0 and h > 0 and area else 0.0


def merge(candidates: list[CandidateObject]) -> list[CandidateObject]:
    """Drop an OCR block that sits (>= 80%) inside a structured candidate whose text already contains it."""
    structured = [c for c in candidates if c.source in STRUCTURED]
    kept = []
    for candidate in candidates:
        if candidate.source == "ocr" and any(
            _inside_fraction(candidate.bbox, other.bbox) >= 0.8
            and _norm(candidate.text) in _norm(other.text)
            for other in structured
        ):
            continue
        kept.append(candidate)
    return kept[:MAX_CANDIDATES]
