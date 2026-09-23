"""Client-agnostic Spatial contract (protocol v3). Every client — browser extension, desktop app — describes an
ask as a SpatialContext; the server never branches on which client sent it. Also converts the v2 extension payload
and adapts contexts to the deterministic resolver (whose scoring must stay identical to extension/geometry.js)."""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import models_json_schema

MarkKind = Literal["point", "rectangle", "circle", "polygon", "arrow", "line"]
MarkRole = Literal["reference", "source", "target"]
CandidateSource = Literal["dom", "pdf_text", "ocr", "uia", "vision"]
SurfaceKind = Literal["web", "pdf", "desktop"]
PrivacyPolicy = Literal["anchors_only", "crop_only", "full_frame"]

_KINDS = set(get_args(MarkKind))
_ROLES = set(get_args(MarkRole))
_POLICIES = set(get_args(PrivacyPolicy))
_SURFACES = set(get_args(SurfaceKind))


class BBox(BaseModel):
    """CSS/logical px of the surface the mark was drawn on. x/y may be negative (element partly off-screen)."""

    model_config = ConfigDict(allow_inf_nan=False)

    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class SpatialMark(BaseModel):
    mark_id: str | None = None
    kind: MarkKind
    role: MarkRole = "reference"
    bbox: BBox
    points: list[tuple[float, float]] | None = Field(default=None, max_length=2000)
    closed: bool | None = None


class Provenance(BaseModel):
    extractor: str
    extractor_version: str = "1"


class CandidateObject(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    source: CandidateSource
    object_type: str | None = None
    role: str | None = None
    label: str | None = None
    text: str = Field(default="", max_length=1500)
    bbox: BBox
    page: int | None = None
    href: str | None = None
    src: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance


class Viewport(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class Surface(BaseModel):
    kind: SurfaceKind = "web"
    url: str = Field(default="", max_length=2000)
    title: str = Field(default="", max_length=500)
    app: str | None = None
    process: str | None = None
    window_title: str | None = None
    viewport: Viewport
    device_pixel_ratio: float = Field(default=1.0, gt=0)


class CropInfo(BaseModel):
    """Region of the surface the attached image covers, and image px per surface px."""

    bbox: BBox
    scale: float = Field(gt=0)


class SpatialContext(BaseModel):
    surface: Surface
    marks: list[SpatialMark] = Field(min_length=1, max_length=8)
    candidates: list[CandidateObject] = Field(default_factory=list, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    privacy_policy: PrivacyPolicy = "crop_only"
    crop: CropInfo | None = None


class Alternative(BaseModel):
    candidate_id: str
    score: float


class SemanticResolution(BaseModel):
    selected_candidate_id: str | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    geometric_confidence: float
    semantic_confidence: float | None = (
        None  # filled by the System-One resolver (sub-project 2)
    )
    confidence: float
    abstained: bool
    resolver: str
    latency_ms: int


def _text(value: Any) -> str:
    """Browser text can end in half an emoji (JS slices UTF-16); replace lone surrogates so validation passes."""
    return str(value or "").encode("utf-8", "replace").decode("utf-8")


# --- v2 (browser extension) -> v3 ----------------------------------------------------------------------------


def _mark_from_v2(raw: Any) -> SpatialMark | None:
    if not isinstance(raw, dict) or raw.get("type") not in _KINDS:
        return None
    try:
        points = raw.get("points")
        pts = (
            [(float(p[0]), float(p[1])) for p in points][:2000]
            if isinstance(points, list) and points
            else None
        )
        if all(axis in raw for axis in ("x", "y", "width", "height")):
            x, y, w, h = (float(raw[axis]) for axis in ("x", "y", "width", "height"))
        elif pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        elif "x" in raw and "y" in raw:
            x, y = float(raw["x"]), float(raw["y"])
            w, h = float(raw.get("width") or 0), float(raw.get("height") or 0)
        else:
            return None
    except (TypeError, ValueError, IndexError):
        return None
    # The resolver clamps mark origins and sizes to >= 0; do the same so both paths see the same box.
    box = BBox(x=max(0.0, x), y=max(0.0, y), width=max(0.0, w), height=max(0.0, h))
    return SpatialMark(
        mark_id=str(raw["id"]) if raw.get("id") else None,
        kind=raw["type"],
        role=raw.get("role") if raw.get("role") in _ROLES else "reference",
        bbox=box,
        points=pts,
        closed=raw["closed"] if isinstance(raw.get("closed"), bool) else None,
    )


def _candidate_from_v2(raw: Any, surface_kind: str) -> CandidateObject | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    box = raw.get("bbox") or raw.get("rect")
    if not isinstance(box, dict):
        return None
    try:
        bbox = BBox(
            x=float(box.get("x", 0)),
            y=float(box.get("y", 0)),
            width=max(0.0, float(box.get("width", 0))),
            height=max(0.0, float(box.get("height", 0))),
        )
    except (TypeError, ValueError):
        return None
    kind = str(raw.get("type", "unknown"))
    page = raw.get("page")
    page = (
        int(page)
        if isinstance(page, (int, float)) and not isinstance(page, bool)
        else None
    )
    if kind == "ocr":
        source = "ocr"
    elif surface_kind == "pdf" or page is not None:
        source = "pdf_text"
    else:
        source = "dom"
    return CandidateObject(
        candidate_id=str(raw["id"])[:200],
        source=source,
        object_type=kind,
        text=_text(raw.get("text"))[:1500],
        bbox=bbox,
        page=page,
        href=str(raw["href"])[:500] if raw.get("href") else None,
        src=str(raw["src"])[:500] if raw.get("src") else None,
        provenance=Provenance(extractor="extension-v2"),
    )


def from_v2(
    *,
    question: str,
    marks: list[dict],
    anchors: list[dict],
    canvas: dict | None,
    page: dict,
    privacy_policy: str,
    crop: CropInfo | None = None,
) -> SpatialContext:
    surface_kind = page.get("surface") if page.get("surface") in _SURFACES else "web"
    converted = [m for m in (_mark_from_v2(raw) for raw in marks) if m is not None][:8]
    if not converted:
        raise ValueError("no usable marks")
    candidates = [
        c
        for c in (_candidate_from_v2(raw, surface_kind) for raw in anchors)
        if c is not None
    ][:200]
    canvas = canvas or {}
    viewport = {
        "width": max(float(canvas.get("width") or 1), 1.0),
        "height": max(float(canvas.get("height") or 1), 1.0),
    }
    return SpatialContext(
        surface=Surface(
            kind=surface_kind,
            url=_text(page.get("url"))[:2000],
            title=_text(page.get("title"))[:500],
            viewport=viewport,
        ),
        marks=converted,
        candidates=candidates,
        question=_text(question),
        privacy_policy=privacy_policy
        if privacy_policy in _POLICIES
        else "anchors_only",
        crop=crop,
    )


# --- adapters to the deterministic resolver and the answer layer --------------------------------------------


def mark_to_v2(mark: SpatialMark) -> dict:
    out: dict[str, Any] = {
        "type": mark.kind,
        "role": mark.role,
        "x": mark.bbox.x,
        "y": mark.bbox.y,
    }
    # A v2 point arrives without a size and must not trip the resolver's zero-size penalty.
    if mark.kind != "point" or mark.bbox.width or mark.bbox.height:
        out.update(width=mark.bbox.width, height=mark.bbox.height)
    if mark.points:
        out["points"] = [[x, y] for x, y in mark.points]
    if mark.closed is not None:
        out["closed"] = mark.closed
    return out


def candidate_to_anchor(candidate: CandidateObject) -> dict:
    return {
        "id": candidate.candidate_id,
        "type": candidate.object_type or candidate.source,
        "text": candidate.text,
        "bbox": candidate.bbox.model_dump(),
        "page": candidate.page,
        "href": candidate.href or "",
        "src": candidate.src or "",
        "source": candidate.source,
    }


def resolver_inputs(ctx: SpatialContext) -> tuple[list[dict], dict, list[dict]]:
    return (
        [mark_to_v2(m) for m in ctx.marks],
        {"width": ctx.surface.viewport.width, "height": ctx.surface.viewport.height},
        [candidate_to_anchor(c) for c in ctx.candidates],
    )


def page_dict(ctx: SpatialContext) -> dict:
    """The page shape the answer layer and SQLite history already use."""
    title = ctx.surface.title or ctx.surface.window_title or ctx.surface.app or ""
    return {"url": ctx.surface.url, "title": title, "surface": ctx.surface.kind}


def to_semantic_resolution(resolution: dict) -> SemanticResolution:
    alternatives, seen = [], set()
    for candidate in resolution.get("candidates", []):
        for ranked in candidate.get("anchors_ranked", []):
            if ranked["id"] not in seen:
                seen.add(ranked["id"])
                alternatives.append(
                    Alternative(candidate_id=ranked["id"], score=ranked["score"])
                )
    first = (resolution.get("candidates") or [{}])[0]
    confidence = float(resolution.get("confidence", 0.0))
    return SemanticResolution(
        selected_candidate_id=first.get("anchor_id"),
        alternatives=alternatives,
        geometric_confidence=confidence,
        confidence=confidence,
        abstained=confidence < 0.6,
        resolver=str(resolution.get("resolver", "deterministic-v1")),
        latency_ms=int(resolution.get("latency_ms", 0)),
    )


def schema_document() -> dict:
    """JSON Schema shared with the JS and Rust clients (written by scripts/export_schema.py)."""
    _, schema = models_json_schema(
        [(SpatialContext, "validation"), (SemanticResolution, "serialization")],
        title="Spatial protocol v3",
    )
    return schema
