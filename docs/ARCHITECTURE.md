# Architecture

*Living document: describes the system **as it is**, then **where it is going**. Update it in the same commit
as any change that makes it wrong.*
**Last updated:** 2026-09-23

## 1. Current system (v0.3, browser)

```
Browser tab / pdf.js viewer                 Service worker                     server (FastAPI :8787)
┌──────────────────────────┐   messages   ┌────────────────────┐   HTTP    ┌────────────────────────┐
│ content.js overlay       │ ───────────▶ │ background.js      │ ────────▶ │ /api/ask, /ask/stream  │
│  pen / circle / box      │  capture     │  captureVisibleTab │           │  resolver.py  (rank)   │
│  ask panel, mic, speaker │  ask         │  crop (Offscreen)  │           │  ocr.py       (crop)   │
│  anchors: DOM / PDF text │  speak       │  token, privacy    │           │  research.py  (cite)   │
│ geometry.js (shared)     │  transcribe  │  PDF → viewer.html │           │  providers.py (LLMs)   │
└──────────────────────────┘              └────────────────────┘           │  store.py     (SQLite) │
                                                                            │ /api/stt  faster-whisper│
                                                                            │ /api/tts  pocket-tts    │
                                                                            └────────────────────────┘
```

**Mark** — `{type: polygon|circle|rectangle|point, points?, x, y, width, height, role}` in viewport CSS px.

**Anchor** — `{id, type, text, bbox, page?, href?, src?}`: a DOM element or merged PDF text block under the
mark. Collected client-side (`elementsFromPoint` 6×6 grid; page-sized containers filtered by `anchorFilter`);
ranked by `geometry.js::rankAnchors` and identically by `resolver.py::resolve_marks` (IoU / containment,
tie-break longer text then smaller area). Golden cases in `server/tests/cases/` keep JS and Python in parity.

**Ask flow** (`main.py::prepare_ask` → `providers.py::answer_stream` → `finish_ask`):
1. Convert the request to a `SpatialContext` (v3 as-is; v2 via `contracts.from_v2`), drop `image_data` unless the
   privacy tier allows; OCR blocks become placed candidates when the crop's geometry is attached (`candidates.py`).
2. `resolve_marks` → ranked anchors + hand-tuned confidence (`0.78 + 0.18·matched/marks`; `< 0.6` →
   `confirmation_required`).
3. **System One judgment (Jev, `semantic.py` + `system_one.py`)**: one request picks the target (hybrid: Jev's
   pick when its probability ≥ 0.5, else geometry), flags ambiguity (→ "Did you mean" chips), and routes: help mode,
   research only when outside facts are needed (≥ 0.8), vision only when visual (≥ 0.5), follow-up same-target reuse.
   Any failure/timeout (1.5 s) → geometry-only, research as requested.
   **Data sent to TypeSafe per ask:** the question, previous question, page kind and up to 8 shortlisted element
   texts (≤ 300 chars, `data:`/base64 scrubbed) — never pixels. Sent even when a local answer model is chosen;
   opt out with `SPATIAL_SYSTEM_ONE=off`.
4. Optional research (`research.py`, after the Cited Multi-Agent Researcher): one query, or one per mark for a
   `compare` ask → **Tavily** `fast` search (ranked chunks; `TAVILY_API_KEY`) or DuckDuckGo + page fetch fallback →
   dedupe + credibility → **Jev passage ranking** → numbered sources. After the answer, **Jev checks each citation**
   (`citation_checks`, `unsupported_citations` → ⚠ in the extension). Gemini removed.
5. Provider chain (`SPATIAL_PROVIDERS` order): vision model gets the crop; text models get OCR text. First
   provider that answers wins; if none, deterministic fallback quotes the marked text.
6. Persist context + turn history in SQLite; follow-ups pass `context_id`.

**Contract** — `server/app/contracts.py` (protocol v3, v2 still accepted); JSON Schema in `schema/spatial-context.v3.json`.

**Trace log** — `server/app/trace.py`: opt-in JSONL per ask (no pixels), `/api/traces/*`.

**Eval** — `server/app/evaluation.py` + `scripts/eval.py` over `server/tests/cases` + `server/tests/eval_cases`;
baseline in `server/tests/eval_baseline.json` (2026-09-23: top-1 92%, top-3 100%, abstain 0%).

**Privacy tiers** — `anchors_only` (no pixels), `crop_only` (default; marked region + 28 px, ≤1600 px JPEG),
`full_frame`. Enforced in service worker and again on server. *Not a current investment priority.*

**Safety** — an ask never triggers actions. Output is text (optionally spoken) + highlight.

## 2. Target architecture

```
 INPUT        hotkey · mark (freehand/circle/box/point) · question (text/voice)
   │
 CLIENT       browser extension  |  desktop app (Tauri: freeze-frame overlay, global hotkey)
   │          candidate providers: DOM · PDF text · UIA (Windows) · AX (macOS) · OCR blocks · vision
   ▼
 CONTRACT     SpatialContext { surface, marks[], candidates[], question, crop? }   (protocol v3, JSON Schema)
   ▼
 SERVER       1. merge/dedupe candidates  2. deterministic geometry prefilter (top ~12)
              3. System-One resolver (Jev / Laya via /v1/systemone): which object? ambiguous? mode?
                 needs research? needs vision? same object as last turn?   → fallback: geometry only
              4. context assembler → answer/research layer (LLM/VLM)  5. store + opt-in trace log
   ▼
 OUTPUT       answer · highlight resolved target · alternatives / "which one?" · citations · voice
```

Principles:
- **Geometry answers "where", System One answers "which", the LLM answers "what does it mean".**
  Numbers and geometry stay in code (Jev is weak at arithmetic); System One sees qualitative relations
  ("fully inside the mark", "partial overlap") and text.
- **One candidate shape for every source** (`CandidateObject.source = dom | pdf_text | ocr | uia | vision`).
  The server never branches on client type.
- **Coordinates:** everything in the contract is CSS/logical px of the surface the mark was drawn on
  (browser viewport, or the frozen monitor frame on desktop). Clients convert device px / DPI before sending.
- **Resolver backends are swappable** behind one `/v1/systemone` client: Jev (TypeSafe, paid API),
  Laya (open weights; hosted by impossibl or self-hosted `laya-serve`), deterministic fallback.
- **Traces are data:** opt-in JSONL trace log (no pixels) feeds the eval harness and, later, Laya fine-tuning.

### Desktop app (sub-project 4; 4a server built, 4b Tauri app next)

Server owns pixels and OS access (`server/app/desktop.py`): `POST /api/desktop/capture` freezes the monitor under the
cursor (in memory, last 3, 5 min TTL); `POST /api/desktop/candidates` reads UIA elements under a point grid in the mark
(+ TextPattern lines) from the topmost non-excluded, non-cloaked window, never from password managers, OCR as fallback;
`Ask.capture_id` makes the server crop the frozen frame. The Tauri app only draws and asks.

| Browser piece | Desktop equivalent (Windows first) |
|---|---|
| `chrome.commands` hotkey | `RegisterHotKey` global hotkey |
| `captureVisibleTab` | Windows.Graphics.Capture / DXGI of monitor under cursor |
| content-script overlay | Freeze-frame: capture first, show it full-screen, draw on the still image |
| DOM anchors | UI Automation elements (name, control type, value, bounding rect) |
| PDF text layer | UIA TextPattern, else OCR blocks |
| site blocklist | process/app blocklist + windows excluded from capture |

Known limits: canvas/game/video/remote-desktop apps expose no UIA → OCR/vision candidates; elevated (admin)
windows are unreadable from a non-elevated process; Electron apps expose UIA only once accessibility is on.
Optional bridge: when the window is Chrome with the extension installed, fetch DOM candidates from it.

## 3. Module reuse

`server/app/resolver.py`, `providers.py`, `ocr.py`, `audio.py` have no FastAPI dependency.
`extension/geometry.js` is a plain script usable in any page and under `node:test`.

## 4. Sub-project status

See `TASKS.md`. Specs: `docs/superpowers/specs/`.
