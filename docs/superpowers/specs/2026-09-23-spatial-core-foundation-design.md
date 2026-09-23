# Spatial Core Foundation — Design

**Date:** 2026-09-23
**Status:** Implemented (2026-09-23, branch `feat/core-foundation`)
**Sub-project:** 1 of 5 (see "Roadmap context")

## Goal

Make Spatial an independent product with one client-agnostic contract, so the browser extension today and a
desktop (OS-level) client later feed the same server pipeline; add an opt-in trace log and an eval harness
that give every later change (Jev resolver, desktop candidates) a measurable baseline.

## Roadmap context

| # | Sub-project | Depends on |
|---|---|---|
| 1 | **Core foundation (this spec)** | — |
| 2 | System-One resolver over the `/v1/systemone` protocol: Jev first, Laya (hosted or self-hosted) as second backend, deterministic fallback | 1 |
| 3 | Windows UIA spike (throwaway: hotkey → freeze-frame → box → UIA dump → `/api/ask`) | — |
| 4 | Desktop app (Tauri, Windows first, macOS next) | 1, 3 |
| 5 | Desktop ↔ extension bridge, macOS AX | 4 |

Decisions already made: Windows first with a stack that ports to macOS (Tauri); Jev is used as a System-One
helper, never as the answerer (Laya speaks the same protocol and is evaluated alongside it); cloud APIs are acceptable, local/privacy-first is not a current priority; trace logging captures metadata + resolution trace, never pixels.

## Non-goals

- No Jev calls (sub-project 2).
- No desktop client, UIA code, or native capture (sub-projects 3–4).
- No repository-wide refactor into the master plan's §56 tree; only the files listed below change.
- No change to answer providers, research, audio, or the SQLite history schema.
- No new browser extraction work (shadow DOM, iframes, SVG grouping).

---

## A. Independence — remove StudyOS

This repo becomes the single source of truth. Nothing is synced in or out.

| File | Change |
|---|---|
| `extension/config.js` | Drop `dashboardUrl`, `paths.login/register/quiz`, `features.accounts/quizLater`, `anonymousDailyLimit`; rewrite header comment. `mode` removed (always standalone). |
| `extension/background.js` | Remove `email` default, `quizLater()` and the `spatial:quiz` message case. |
| `extension/content.js` | Remove `attachQuiz` and its call; consent text loses the accounts branch. |
| `extension/popup.html` / `popup.js` | Remove sign-in block (email, password, login, register link, sign-out, dashboard button), `CFG.mode === 'studyos'` branches, `email` from `KEYS`. Token field always shown. |
| `extension/detect.js` | Delete (dashboard-only; not referenced by `manifest.json`). |
| `extension/geometry.js` | Drop `root.StudyOSGeometry` alias; comments reference `server/app/resolver.py` and `server/tests/cases`. |
| `server/app/resolver.py`, `server/tests/test_resolver_cases.py` | Replace "SYNCED from StudyOS" docstrings. |
| `README.md` | Remove "Origin and sync"; add short "Tracing" and "Eval" sections. |
| `docs/SPATIAL_PRODUCTION_CHECKLIST.md`, `docs/LEARNING_PATH.md` | Remove StudyOS references. |

Done when `grep -riE "studyos|sync_spatial|quiz|learning-platform" extension server README.md docs` returns nothing.

## B. Contract — `server/app/contracts.py`

Pydantic v2 models, trimmed from master plan §3 to fields used now. All boxes are **viewport CSS px of the
surface the mark was drawn on** (browser viewport today; the frozen monitor frame for the desktop client later).

```python
BBox            = {x, y, width, height: float >= 0}
CandidateSource = Literal["dom", "pdf_text", "ocr", "uia", "vision"]

SpatialMark:      mark_id?, kind: point|rectangle|circle|polygon|arrow|line,
                  role: reference|source|target (default reference),
                  bbox: BBox, points?: list[[x, y]] (<=2000), closed?: bool
CandidateObject:  candidate_id, source: CandidateSource, object_type?, role?, label?, text (<=1500),
                  bbox: BBox, page?: int, href?, src?, attributes?: dict[str, str],
                  provenance: {extractor: str, extractor_version: str}
Surface:          kind: web|pdf|desktop, url?, title?, app?, process?, window_title?,
                  viewport: {width, height}, device_pixel_ratio: float = 1
CropInfo:         bbox: BBox (region of the surface the crop covers), scale: float
SpatialContext:   marks, candidates, surface, question, privacy_policy, crop?: CropInfo
SemanticResolution: selected_candidate_id?, alternatives: [{candidate_id, score}], geometric_confidence,
                  semantic_confidence? (None until sub-project 2), confidence, abstained: bool,
                  resolver: str, latency_ms
```

`scripts/export_schema.py` writes `schema/spatial-context.v3.json` (JSON Schema from the models) so the JS
extension and the future Rust client validate against the same shape. A test fails if the committed schema
differs from the generated one.

### Protocol v3, v2 kept

- `PROTOCOL_VERSION = 3`, `MIN_PROTOCOL_VERSION = 2`. `check_protocol` rejects only `< 2`.
- **v2 payload (today's extension, unchanged):** `marks` + `anchors` + `canvas` + `page`. A new
  `contracts.from_v2(payload) -> SpatialContext` converts: anchor → `CandidateObject` (`source` = `pdf_text`
  when `page.surface == "pdf"` or anchor has `page`, else `dom`; `candidate_id` = anchor id); mark x/y/w/h →
  `bbox`; `canvas` → `surface.viewport`.
- **v3 payload:** `{protocol_version: 3, context: SpatialContext, context_id?, provider?, research?, level?, image_data?}`.
- Internally `prepare_ask` works on `SpatialContext` only. `resolve_marks` keeps its current signature and
  scoring (golden parity with `geometry.js` must not change); an adapter feeds it candidates as anchor dicts.
- Response gains `resolution_v3: SemanticResolution`; existing response fields stay for the v2 extension.

## C. Candidate sources — OCR blocks become candidates

`server/app/ocr.py`:

- New `ocr_blocks(image_data) -> list[{text, bbox, confidence}]` (bbox in crop px; keeps RapidOCR boxes,
  confidence >= 0.4).
- `ocr_image()` becomes `"\n".join(block.text ...)` over `ocr_blocks()` — same output as today.

`server/app/candidates.py` (new):

- `ocr_candidates(blocks, crop: CropInfo | None) -> list[CandidateObject]`: when `crop` is given, map each
  box to surface coords (`surface = crop.bbox.xy + crop_px / crop.scale`) and emit `source="ocr"` candidates;
  without `crop`, return `[]` (OCR text still reaches the prompt as today).
- `merge(candidates) -> list[CandidateObject]`: drop an OCR candidate whose bbox has IoU >= 0.5 with a
  `dom`/`pdf_text`/`uia` candidate whose text matches after whitespace/case normalisation (structured
  sources win). Cap at 64 candidates.

OCR candidates run only when an image is attached (privacy `crop_only`/`full_frame`) and OCR is enabled.

Extension change: `background.js` already knows the crop box, padding and scale; it sends
`crop: {bbox, scale}` alongside `image_data` in the v2 payload (additive field, ignored by old servers).

## D. Trace log — `server/app/trace.py`

Opt-in, local, separate from `spatial.db`. **Never contains image bytes.**

- **Location:** `SPATIAL_LOG_DIR`, default `%APPDATA%\Spatial\logs` on Windows,
  `~/Library/Logs/Spatial` on macOS, `$XDG_STATE_HOME/spatial/logs` (fallback `~/.local/state/spatial/logs`) elsewhere.
- **Switch:** `SPATIAL_TRACE=off|on` (default `off`); `SPATIAL_TRACE_MAX_MB` (default 50),
  `SPATIAL_TRACE_RETENTION_DAYS` (default 14). The popup gets a "Keep a local trace log" toggle that calls
  `PUT /api/traces/config {enabled}` (runtime override, persisted to `<log dir>/config.json`).
- **Format:** one JSON object per ask, appended to `YYYY-MM-DD.jsonl`:

```json
{"trace_version": 1, "request_id": "uuid", "at": "ISO-8601", "context_id": "...",
 "client": {"protocol": 2, "version": "0.3.0"}, "surface": {...SpatialContext.surface},
 "privacy_policy": "crop_only", "image_attached": true,
 "marks": [...], "candidates": [...], "resolution": {...SemanticResolution},
 "question": "...", "answer": "...", "provider": "ollama", "model": "qwen3:4b-instruct",
 "timings_ms": {"resolve": 3, "ocr": 180, "research": 0, "answer": 2400, "total": 2610},
 "errors": {}, "cost_usd": 0.0}
```

- `image_data` is removed by an allowlist serializer (only the keys above are written), not by deleting a key.
- **Retention:** on startup and after each write, delete files older than retention; if the directory exceeds
  the size cap, delete oldest files first.
- **Endpoints (token-protected like the rest):** `GET /api/traces/config`, `PUT /api/traces/config`,
  `GET /api/traces/export` (streams all `.jsonl` concatenated), `DELETE /api/traces` (removes all files).
- `/api/health` reports `trace: {enabled, dir, size_mb}`.

## E. Eval harness

- Golden cases grow from 7 to **~50** in `server/tests/cases/`: 20 web DOM, 15 PDF text, 8 ambiguous
  (two plausible candidates; expected = either, flagged `ambiguous: true`), 7 OCR-only (candidates with
  `source: "ocr"`). Each case: `{name, context (v3), expected_candidate_ids, ambiguous?}`. Existing 7 cases are
  converted, not dropped; the JS/Python parity test keeps running on DOM/PDF cases.
- `scripts/eval.py`:
  - `python scripts/eval.py cases` — runs resolver over golden cases.
  - `python scripts/eval.py traces <dir>` — replays trace records (uses the trace's candidates; expected =
    trace's selected candidate unless the record carries a `label` field added by hand).
  - Reports top-1, top-3, abstain rate, p50/p95 resolver latency; `--json` for machine output;
    `--baseline <file>` exits non-zero if top-1 drops by more than 2 points.
- Baseline committed as `server/tests/eval_baseline.json` — the bar sub-project 2 must beat.

---

## Error handling

| Situation | Behaviour |
|---|---|
| Trace dir not writable / disk full | Log one warning, disable tracing for the process, `/api/health.trace.error` set. Ask still succeeds. |
| Trace write raises | Swallowed after warning; never fails an ask. |
| v3 payload fails validation | 422 with `{code: "BAD_CONTEXT", message}` (FastAPI detail normalised to the existing error shape). |
| Protocol < 2 | 426 `CLIENT_OUTDATED` (unchanged). |
| OCR not installed / crop undecodable | `ocr_blocks` returns `[]`; no OCR candidates; ask continues. |
| Crop info missing with image | OCR text only, no OCR candidates. |
| `DELETE /api/traces` while writing | Writes use a module lock; delete takes the same lock. |

## Testing

- `test_contracts.py`: v2→SpatialContext conversion for DOM, PDF, polygon, point marks; v3 round-trip;
  schema file matches generated schema.
- `test_protocol.py`: v2 and v3 `/api/ask` return equivalent resolution for the same case; protocol 1 → 426.
- `test_candidates.py`: crop→surface mapping with scale ≠ 1; merge drops duplicate OCR, keeps unique OCR.
- `test_trace.py`: off by default writes nothing; on writes one line per ask; **no `image_data`/base64 in any
  line** (regex scan for `data:image` and long base64 runs); retention and size cap; export and delete; unwritable
  dir does not fail the ask.
- `test_resolver_cases.py`: all ~50 cases load; parity with `geometry.js` on DOM/PDF cases.
- `node --test extension/tests/geometry.test.mjs` stays green.
- Manual: load extension, ask on a web page and a PDF, toggle trace in popup, confirm a `.jsonl` line appears
  without image data; run `scripts/eval.py cases`.

## Files touched

New: `server/app/contracts.py`, `server/app/candidates.py`, `server/app/trace.py`, `scripts/eval.py`,
`scripts/export_schema.py`, `schema/spatial-context.v3.json`, `server/tests/eval_baseline.json`,
tests listed above, ~43 new case files.
Modified: `server/app/main.py`, `server/app/ocr.py`, `server/app/config.py`, `server/app/resolver.py` (docstring),
extension files in section A, `README.md`, `docs/SPATIAL_PRODUCTION_CHECKLIST.md`, `docs/LEARNING_PATH.md`, `docs/ARCHITECTURE.md`.
Deleted: `extension/detect.js`.

## Implementation notes (deviations from this spec)

- `BBox.x/y` may be negative (elements scrolled partly off-screen); only width/height are `>= 0`.
- OCR dedupe: drop an OCR block that is >= 80% inside a structured candidate whose text contains the OCR text
  (exact-text + IoU matching almost never fires, since OCR returns lines and DOM returns paragraphs).
- Eval cases live in `server/tests/eval_cases/` (generated by `generate.py`, labelled `intended`); golden cases stay
  in `server/tests/cases/` and are normalized on load. JS/Python parity runs over both sets.
- Trace retention runs after each write (no startup pass).
- A request without `protocol_version` is treated as v2 (v3 is detected by version >= 3 or a `context` field).
- v2 marks of unknown type are dropped; if none remain the ask is `400 NO_MARKS` (previously answered unresolved).
