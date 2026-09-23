"""Spatial — Point & Ask server. Circle anything in the browser or a PDF, ask, get an answer about
exactly that region. Single-user local tool: no accounts, optional bearer token, SQLite history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app import store
from app.audio import audio_status, synthesize, transcribe
from app.candidates import merge, ocr_candidates
from app.config import settings
from app.contracts import (CropInfo, SpatialContext, from_v2, mark_to_v2, page_dict, resolver_inputs,
                           to_semantic_resolution)
from app import research
from app.ocr import ocr_blocks
from app.providers import answer_stream, clean_answer, provider_status
from app.resolver import resolve_marks

PROTOCOL_VERSION = 3  # v3: SpatialContext payload; bump when the ask payload/response shape changes incompatibly
MIN_PROTOCOL_VERSION = 2  # the v2 browser extension payload is still accepted and converted

app = FastAPI(title="Spatial — Point & Ask", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^(chrome|moz)-extension://.*$",
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Keep the {code, message} error shape clients already handle."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    code = "BAD_CONTEXT" if any("context" in map(str, e.get("loc", ())) for e in errors) else "BAD_REQUEST"
    where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    return JSONResponse(status_code=422, content={"detail": {"code": code, "message": f"{where}: {first.get('msg', 'invalid request')}"}})


class Page(BaseModel):
    url: str = Field(default="", max_length=2000)
    title: str = Field(default="", max_length=500)
    surface: str = Field(default="web", max_length=30)


class Ask(BaseModel):
    # v2 fields (browser extension today)
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    marks: list[dict] = Field(default_factory=list)
    canvas: dict[str, float] | None = None
    anchors: list[dict] = Field(default_factory=list)
    page: Page = Field(default_factory=Page)
    crop: CropInfo | None = None  # where the attached crop sits on the page (enables OCR candidates)
    # v3: the whole ask as one SpatialContext
    context: SpatialContext | None = None
    # shared
    context_id: str | None = None
    provider: str | None = None
    privacy_policy: str = Field(default="crop_only", max_length=30)
    image_data: str | None = Field(default=None, max_length=8_000_000)
    protocol_version: int = MIN_PROTOCOL_VERSION  # omitted version = v2 payload; v3 is also detected from `context`
    client_version: str | None = Field(default=None, max_length=40)
    research: bool = False  # ground the answer in web sources (app/research.py) and cite them
    level: str | None = Field(default=None, max_length=10)  # eli5 | student | expert


class Speak(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = None


def require_token(request: Request) -> None:
    if not settings.api_token:
        return
    authorization = request.headers.get("Authorization", "")
    if authorization != f"Bearer {settings.api_token}":
        raise HTTPException(
            401, {"code": "AUTH_REQUIRED", "message": "invalid or missing API token"}
        )


def anchors_used(resolution: dict, anchors: list[dict]) -> list[dict]:
    """Anchors the resolver ranked, carrying the role of the mark they belong to (reference/source/target)
    and the mark index so the client can highlight the resolved target."""
    lookup = {
        str(anchor.get("id")): anchor
        for anchor in anchors
        if isinstance(anchor, dict) and anchor.get("id")
    }
    used, seen = [], set()
    for candidate in resolution["candidates"]:
        for ranked in candidate.get("anchors_ranked", []):
            if ranked["id"] in seen or ranked["score"] < 0.25:
                continue
            seen.add(ranked["id"])
            source = lookup.get(ranked["id"], {})
            used.append(
                {
                    "id": ranked["id"],
                    "type": ranked["type"],
                    "text": str(source.get("text") or "")[:1500],
                    "score": ranked["score"],
                    "page": ranked.get("page"),
                    "href": str(source.get("href") or "")[:500],
                    "src": str(source.get("src") or "")[:500],
                    "role": candidate.get("role", "reference"),
                    "mark_index": candidate.get("mark_index", 0),
                    "bbox": source.get("bbox"),
                }
            )
    return used


def check_protocol(payload: Ask) -> None:
    if payload.protocol_version < MIN_PROTOCOL_VERSION:
        raise HTTPException(
            426,
            {
                "code": "CLIENT_OUTDATED",
                "message": f"client speaks protocol {payload.protocol_version}, server needs >= {MIN_PROTOCOL_VERSION}; update the client",
            },
        )


def to_context(payload: Ask) -> SpatialContext:
    """Every ask becomes one SpatialContext, whichever client sent it."""
    if payload.protocol_version >= 3 or payload.context is not None:
        if payload.context is None:
            raise HTTPException(
                422, {"code": "BAD_CONTEXT", "message": "protocol 3 requires `context`"}
            )
        return payload.context
    if not payload.marks:
        raise HTTPException(
            400, {"code": "NO_MARKS", "message": "at least one mark is required"}
        )
    if not payload.question:
        raise HTTPException(
            422, {"code": "BAD_CONTEXT", "message": "question is required"}
        )
    try:
        return from_v2(
            question=payload.question,
            marks=payload.marks,
            anchors=payload.anchors,
            canvas=payload.canvas,
            page=payload.page.model_dump(),
            privacy_policy=payload.privacy_policy,
            crop=payload.crop,
        )
    except ValueError:
        raise HTTPException(
            400, {"code": "NO_MARKS", "message": "no usable marks"}
        ) from None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "protocol_version": PROTOCOL_VERSION,
        "providers": provider_status(),
        "provider_order": list(settings.provider_order),
        "ocr": settings.ocr_enabled,
        "audio": audio_status(),
        "auth_required": bool(settings.api_token),
    }


def prepare_ask(payload: Ask) -> dict:
    """Shared front half of ask/ask-stream: validation, contract, resolver, anchors, history, research."""
    started = perf_counter()
    check_protocol(payload)
    ctx = to_context(payload)
    previous = store.get(payload.context_id) if payload.context_id else None
    if payload.context_id and not previous:
        raise HTTPException(
            404, {"code": "CONTEXT_NOT_FOUND", "message": "context not found"}
        )
    image_data = (
        payload.image_data
        if ctx.privacy_policy in {"crop_only", "full_frame"}
        else None
    )
    ocr_text = None
    timings: dict[str, int] = {}
    if image_data and settings.ocr_enabled:
        ocr_started = perf_counter()
        blocks = ocr_blocks(image_data)
        timings["ocr"] = round((perf_counter() - ocr_started) * 1000)
        ocr_text = "\n".join(block["text"] for block in blocks)
        extra = ocr_candidates(blocks, ctx.crop)
        if extra:
            ctx = ctx.model_copy(update={"candidates": merge([*ctx.candidates, *extra])})
    marks, canvas, anchors = resolver_inputs(ctx)
    resolution = resolve_marks(marks, canvas, anchors)
    timings["resolve"] = resolution["latency_ms"]
    resolution.update(
        {
            "surface": ctx.surface.kind,
            "privacy_policy": ctx.privacy_policy,
            "image_attached": bool(image_data),
        }
    )
    used = anchors_used(resolution, anchors)
    history = (previous or {}).get("answer", {}).get("history", [])
    research_started = perf_counter()
    sources = research.gather(ctx.question, used) if payload.research else []
    timings["research"] = round((perf_counter() - research_started) * 1000)
    return {
        "context": ctx,
        "anchors": anchors,
        "previous": previous,
        "image_data": image_data,
        "resolution": resolution,
        "used": used,
        "history": history,
        "sources": sources,
        "started": started,
        "timings": timings,
        "request_id": str(uuid4()),
        "ocr_text": ocr_text,
    }


def finish_ask(payload: Ask, prep: dict, text: str, meta: dict) -> dict:
    """Shared back half: persist the turn and build the response document."""
    ctx: SpatialContext = prep["context"]
    page = page_dict(ctx)
    text = clean_answer(text)
    history = prep["history"] + [
        {
            "question": ctx.question,
            "answer": text,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    ]
    record = {
        "text": text,
        "history": history,
        "anchors_used": prep["used"],
        "sources": prep["sources"],
        "meta": meta,
    }
    if prep["previous"]:
        store.update(prep["previous"]["id"], prep["resolution"], record)
        context_id = prep["previous"]["id"]
    else:
        context_id = store.create(
            page,
            ctx.question,
            [mark_to_v2(m) for m in ctx.marks],
            prep["resolution"],
            record,
        )
    resolution = prep["resolution"]
    return {
        "id": context_id,
        "answer": text,
        "anchors_used": prep["used"],
        "sources": prep["sources"],
        "cited": research.cited_ids(text, prep["sources"]),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "status": meta.get("status"),
        "vision": bool(meta.get("vision")),
        "ocr": bool(meta.get("ocr")),
        "diagram": bool(meta.get("diagram")),
        "level": meta.get("level"),
        "errors": meta.get("errors", {}),
        "note": meta.get("note"),
        "cost_usd": meta.get("cost_usd", 0.0),
        "confidence": resolution["confidence"],
        "confirmation_required": resolution["confidence"] < 0.6,
        "turns": len(history),
        "page": page,
        "resolution": resolution,
        "resolution_v3": to_semantic_resolution(resolution).model_dump(),
        "latency_ms": round((perf_counter() - prep["started"]) * 1000),
        "protocol_version": PROTOCOL_VERSION,
    }
@app.post("/api/ask", dependencies=[Depends(require_token)])
def ask(payload: Ask):
    """The mark is a reference, never authority: this endpoint only explains."""
    prep = prepare_ask(payload)
    parts: list[str] = []
    meta: dict = {}
    for item in answer_stream(
        prep["context"].question,
        page_dict(prep["context"]),
        prep["used"],
        prep["image_data"],
        prep["history"],
        payload.provider,
        prep["sources"],
        payload.level,
        precomputed_ocr=prep["ocr_text"],
    ):
        if isinstance(item, dict):
            meta = item
        else:
            parts.append(item)
    return finish_ask(payload, prep, "".join(parts), meta)


@app.post("/api/ask/stream", dependencies=[Depends(require_token)])
def ask_stream(payload: Ask):
    """SSE: `status` -> many `delta` {text} -> `complete` (same document as /api/ask) or `error` {code, message}."""

    def event(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n"

    def events():
        try:
            prep = prepare_ask(payload)
        except HTTPException as exc:
            detail = (
                exc.detail
                if isinstance(exc.detail, dict)
                else {"code": "BAD_REQUEST", "message": str(exc.detail)}
            )
            yield event("error", detail)
            return
        yield event(
            "status",
            {
                "status": "resolving_mark",
                "anchors": len(prep["used"]),
                "confidence": prep["resolution"]["confidence"],
            },
        )
        parts: list[str] = []
        meta: dict = {}
        try:
            for item in answer_stream(
                prep["context"].question,
                page_dict(prep["context"]),
                prep["used"],
                prep["image_data"],
                prep["history"],
                payload.provider,
                prep["sources"],
                payload.level,
                precomputed_ocr=prep["ocr_text"],
            ):
                if isinstance(item, dict):
                    meta = item
                else:
                    parts.append(item)
                    yield event("delta", {"text": item})
            yield event("complete", finish_ask(payload, prep, "".join(parts), meta))
        except Exception as exc:
            yield event(
                "error",
                {"code": "ASK_FAILED", "message": f"ask failed: {type(exc).__name__}"},
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/contexts", dependencies=[Depends(require_token)])
def contexts(limit: int = 25):
    return store.recent(min(max(limit, 1), 200))


@app.get("/api/contexts/{context_id}", dependencies=[Depends(require_token)])
def context(context_id: str):
    found = store.get(context_id)
    if not found:
        raise HTTPException(
            404, {"code": "CONTEXT_NOT_FOUND", "message": "context not found"}
        )
    return found


@app.delete("/api/contexts/{context_id}", dependencies=[Depends(require_token)])
def delete_context(context_id: str):
    if not store.delete(context_id):
        raise HTTPException(
            404, {"code": "CONTEXT_NOT_FOUND", "message": "context not found"}
        )
    return {"deleted": context_id}


@app.post("/api/stt", dependencies=[Depends(require_token)])
async def speech_to_text(
    audio: UploadFile = File(...), language: str | None = Form(default=None)
):
    """Speech -> text with faster-whisper on CPU. Accepts webm/ogg/wav/mp3 from MediaRecorder."""
    data = await audio.read()
    if not data:
        raise HTTPException(400, {"code": "EMPTY_AUDIO", "message": "empty audio"})
    if len(data) > 25_000_000:
        raise HTTPException(
            413, {"code": "AUDIO_TOO_LARGE", "message": "audio exceeds 25 MB"}
        )
    result = transcribe(data, language)
    if result["status"] != "ok":
        raise HTTPException(
            503,
            {
                "code": "STT_UNAVAILABLE",
                "message": result.get("error", "speech-to-text unavailable"),
            },
        )
    return result


@app.post("/api/tts", dependencies=[Depends(require_token)])
def text_to_speech(payload: Speak):
    """Text -> WAV with Kyutai pocket-tts on CPU."""
    wav, meta = synthesize(payload.text, payload.voice)
    if wav is None:
        raise HTTPException(
            503,
            {
                "code": "TTS_UNAVAILABLE",
                "message": meta.get(
                    "error", meta.get("status", "text-to-speech unavailable")
                ),
            },
        )
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={"X-TTS-Seconds": str(meta["seconds"]), "X-TTS-Voice": meta["voice"]},
    )
