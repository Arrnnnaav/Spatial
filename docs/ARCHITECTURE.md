# Architecture

```
Browser tab / pdf.js viewer                 Service worker                     server (FastAPI)
┌──────────────────────────┐   messages   ┌────────────────────┐   HTTP    ┌────────────────────────┐
│ content.js overlay       │ ───────────▶ │ background.js      │ ────────▶ │ /api/ask               │
│  pen / circle / box      │  capture     │  captureVisibleTab │           │  resolver.py  (rank)   │
│  ask panel, mic, speaker │  ask         │  crop (Offscreen)  │           │  ocr.py       (crop)   │
│  anchors: DOM / PDF text │  speak       │  token, privacy    │           │  providers.py (LLMs)   │
│ geometry.js (shared)     │  transcribe  │  PDF → viewer.html │           │  store.py     (SQLite) │
└──────────────────────────┘              └────────────────────┘           │ /api/stt  faster-whisper│
                                                                            │ /api/tts  pocket-tts    │
                                                                            └────────────────────────┘
```

**Mark** — `{type: polygon|circle|rectangle|point, points?, x, y, width, height, role}` in viewport px.

**Anchor** — `{id, type, text, bbox, page?, href?, src?}`: a DOM element or a merged PDF text block
under the mark. Collected client-side (`elementsFromPoint` grid; page-sized containers filtered);
ranked server-side by IoU / containment (`resolver.py`), tie-break by text length.

**Privacy** — `anchors_only` sends no pixels; `crop_only` (default) sends the marked region (+28 px
padding, ≤1600 px, JPEG); `full_frame` sends the visible tab. Set per user in the popup; enforced in the
service worker and again in the server (`image_data` dropped unless the policy allows it).

**Safety** — an ask never triggers actions. The answer is text (optionally spoken). Extending this to
"do this" workflows should route through explicit permission/confirmation, not through the mark.

**Reuse** — `server/app/resolver.py`, `providers.py`, `ocr.py`, `audio.py` have no FastAPI dependency
and can be imported by another backend; `extension/geometry.js` is a plain script usable in any page.
