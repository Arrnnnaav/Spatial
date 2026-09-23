# Spatial Core Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Spatial independent of StudyOS, route every ask through one client-agnostic `SpatialContext` contract (protocol v3, v2 still accepted), turn OCR blocks into candidates, add an opt-in trace log, and build an eval harness with a committed baseline.

**Architecture:** New focused server modules (`contracts.py`, `candidates.py`, `trace.py`, `evaluation.py`) sit between the FastAPI routes in `main.py` and the unchanged deterministic resolver. `main.py` converts every request (v2 or v3) to a `SpatialContext`, feeds the resolver through an adapter, and writes an allowlisted trace record after each answer. The extension keeps speaking v2 and gains two additive fields (`crop`, trace toggle).

**Tech Stack:** Python 3.12, FastAPI, pydantic 2.13, pytest; vanilla JS Chrome MV3 extension, `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-23-spatial-core-foundation-design.md`

## Global Constraints

- `PROTOCOL_VERSION = 3`, `MIN_PROTOCOL_VERSION = 2`; protocol `< 2` → 426 `CLIENT_OUTDATED`.
- Resolver scoring and `extension/geometry.js` ranking must not change (golden parity).
- Trace log never contains image bytes; default `off`; `SPATIAL_TRACE_MAX_MB=50`, `SPATIAL_TRACE_RETENTION_DAYS=14`.
- Default log dir: Windows `%APPDATA%\Spatial\logs`, macOS `~/Library/Logs/Spatial`, else `$XDG_STATE_HOME/spatial/logs` (fallback `~/.local/state/spatial/logs`); override `SPATIAL_LOG_DIR`.
- Candidate sources: `dom | pdf_text | ocr | uia | vision`. Candidate cap after merge: 64.
- Error bodies keep the existing shape `{"detail": {"code": ..., "message": ...}}`.
- No change to research, audio, or the SQLite schema. Answer providers change only by one optional kwarg (`precomputed_ocr`).
- Run server tests from `server/`: `python -m pytest -q`. Extension tests: `node --test extension/tests/geometry.test.mjs` from repo root.
- Keys never printed or committed. `server/.env` is gitignored.

## Review Focus

1. **Anchor `src` holding a `data:image/...;base64` URL** (inline images on web pages) must not reach the trace log → `trace.build_record` strips `data:` URLs; test in Task 5.
2. **v2 point marks sent without `width`/`height`** must resolve exactly as before (no 0.65 zero-size penalty) → adapter omits zero size for points; test in Task 2.
3. **Anchors with negative `x`/`y`** (elements scrolled partly off-screen) must still be accepted → `BBox.x/y` unconstrained; test in Task 2.
4. **Unwritable or deleted log directory mid-session** must never fail an ask → test in Task 5.
5. **Unknown `privacy_policy` strings from old clients** must fail safe (no image kept) → mapped to `anchors_only`; test in Task 2.

## File Structure

| File | Responsibility |
|---|---|
| `server/app/contracts.py` (new) | Pydantic contract models, v2→v3 conversion, resolver adapter, resolution builder, JSON Schema document |
| `server/app/candidates.py` (new) | OCR blocks → candidates, merge/dedupe |
| `server/app/trace.py` (new) | Opt-in JSONL trace log: enable switch, allowlisted records, retention, export, delete |
| `server/app/evaluation.py` (new) | Load golden/eval cases and traces, run resolver, compute metrics |
| `server/app/main.py` | Routes; `Ask` accepts v2 or v3; `prepare_ask`/`finish_ask` work on `SpatialContext`; trace endpoints |
| `server/app/ocr.py` | `ocr_blocks()` with boxes; `ocr_image()` built on it |
| `server/app/providers.py` | `answer_stream(..., precomputed_ocr=None)` |
| `server/app/config.py` | Trace settings |
| `scripts/export_schema.py`, `scripts/eval.py` (new) | CLIs |
| `schema/spatial-context.v3.json` (new) | Generated JSON Schema |
| `server/tests/eval_cases/generate.py` + `*.json` (new) | 43 labelled eval cases |
| `server/tests/eval_baseline.json` (new) | Committed metrics baseline |
| `extension/*` | StudyOS removal; send `crop`; trace toggle |

---

### Task 1: Remove StudyOS coupling

**Files:**
- Modify: `extension/config.js`, `extension/background.js`, `extension/content.js`, `extension/popup.html`, `extension/popup.js`, `extension/geometry.js`, `server/app/resolver.py:1-3`, `server/tests/test_resolver_cases.py:1-3`, `README.md`, `docs/SPATIAL_PRODUCTION_CHECKLIST.md`, `docs/LEARNING_PATH.md`, `docs/PRD.md`
- Delete: `extension/detect.js`
- Test: `server/tests/test_independence.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `SPATIAL_CONFIG` without `mode`, `dashboardUrl`, `anonymousDailyLimit`, `paths.login/register/quiz`, `features.accounts/quizLater`. Later tasks add `paths.traceConfig`.

- [ ] **Step 1: Write the failing test**

`server/tests/test_independence.py`:

```python
"""Spatial is standalone: no StudyOS coupling may creep back into shipped code or docs."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"studyos|sync_spatial|quiz|learning-platform", re.I)
SCANNED = [ROOT / "extension", ROOT / "server" / "app", ROOT / "server" / "tests", ROOT / "README.md", ROOT / "docs"]
SKIP_PARTS = {"vendor", "__pycache__", ".venv", "superpowers"}
SKIP_FILES = {"test_independence.py", "SPATIAL_STANDALONE_MASTER_PLAN.md", "MEMORY.md", "TASKS.md", "DESIGN.md"}


def scanned_files():
    for base in SCANNED:
        paths = [base] if base.is_file() else base.rglob("*")
        for path in paths:
            if path.is_file() and path.suffix in {".js", ".py", ".html", ".json", ".md"} \
                    and not SKIP_PARTS & set(path.parts) and path.name not in SKIP_FILES:
                yield path


def test_no_studyos_references():
    offenders = [f"{p.relative_to(ROOT)}:{i}" for p in scanned_files()
                 for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
                 if PATTERN.search(line)]
    assert offenders == []


def test_dashboard_detector_removed():
    assert not (ROOT / "extension" / "detect.js").exists()
```

(`MEMORY.md`, `TASKS.md`, `DESIGN.md` and the master plan legitimately record the history of the removal; specs/plans live under `superpowers`.)

- [ ] **Step 2: Run test to verify it fails**

Run (from `server/`): `python -m pytest tests/test_independence.py -v`
Expected: FAIL — offenders list includes `extension/config.js`, `extension/popup.js`, `extension/content.js`, `extension/background.js`, `server/app/resolver.py`, `README.md`, …

- [ ] **Step 3: Rewrite `extension/config.js`**

```js
/* Build-time configuration for the Spatial extension: server URL, API paths and feature flags. */
(function (root) {
  root.SPATIAL_CONFIG = {
    productName: 'Spatial Point & Ask',
    apiBase: 'http://127.0.0.1:8787',
    paths: {
      ask: '/api/ask',
      stream: '/api/ask/stream',
      health: '/api/health',
      transcribe: '/api/stt',
      synthesize: '/api/tts',
    },
    features: {
      providerPicker: true,    // self-hosters choose the provider
      powerMode: true,
    },
    protocolVersion: 2,
  };
})(typeof self !== 'undefined' ? self : this);
```

- [ ] **Step 4: Clean `extension/background.js`**

In `DEFAULTS` remove `email: '', ` (line 10). Delete the whole `async function quizLater(contextId) { … }` (lines 203-208). Delete the line `case 'spatial:quiz': return sendResponse({ ok: true, result: await quizLater(message.contextId) });`. In the `spatial:settings` case replace `signedIn: Boolean(config.token)` with `hasToken: Boolean(config.token)` (grep confirms `signedIn` is read nowhere else).

- [ ] **Step 5: Clean `extension/content.js`**

Line 185 becomes:

```js
      el('p', {}, ['It never runs on banking, health or government sites. You can change this any time from the extension icon.']),
```

Delete the whole `function attachQuiz(actions, contextId) { … }` (lines 366-383) and the call `attachQuiz(actions, result.id);`. Delete the quota block:

```js
      if (result.quota) {
        const q = result.quota;
        note.push((q.signed_in ? '' : 'Free ') + q.remaining + ' of ' + q.limit + ' asks left today');
      }
```

- [ ] **Step 6: Clean `extension/popup.html` and `extension/popup.js`**

`popup.html`: delete the entire `<section id="account" hidden> … </section>` block; change the eyebrow to `<div class="eyebrow" id="eyebrow">SPATIAL</div>`.

`popup.js`: replace lines 1-33 (through the end of `load()`'s account block) and the other StudyOS lines so the file reads:

```js
const CFG = window.SPATIAL_CONFIG;
const $ = id => document.getElementById(id);
const status = (text, kind) => { $('status').textContent = text; $('status').className = 'status ' + (kind || ''); };
const KEYS = ['apiBase', 'token', 'privacy', 'provider', 'voice', 'readAloud', 'research', 'powerMode', 'pdfViewer', 'blocklistExtra', 'deviceId'];

$('title').textContent = CFG.productName;

async function load() {
  const config = await chrome.storage.local.get(KEYS);
  $('apiBase').value = config.apiBase || CFG.apiBase;
  $('token').value = config.token || '';
  $('privacy').value = config.privacy || 'crop_only';
  $('voice').value = config.voice || '';
  $('blocklistExtra').value = config.blocklistExtra || '';
  $('readAloud').checked = Boolean(config.readAloud);
  $('research').checked = config.research !== false;
  $('powerMode').checked = Boolean(config.powerMode);
  $('pdfViewer').checked = Boolean(config.pdfViewer);
  $('providerLabel').hidden = !(CFG.features.providerPicker || config.powerMode);
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $('openPdf').hidden = !(tab && /^(https?|file):\/\/.*\.pdf($|[?#])/i.test(tab.url || ''));
  await health(config.provider || '');
}

async function health(selectedProvider) {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:health', force: true });
  if (!response || !response.ok) {
    status('Cannot reach ' + $('apiBase').value + '. Start the server: cd server && uvicorn app.main:app --port 8787', 'err');
    return;
  }
  const data = response.health;
  const select = $('provider');
  select.innerHTML = '<option value="">Auto (' + (data.provider_order || []).join(' → ') + ')</option>';
  for (const item of data.providers || []) {
    const option = document.createElement('option');
    option.value = item.name; option.disabled = !item.configured;
    option.textContent = item.name + (item.configured ? ' · ' + item.model + (item.vision_model ? ' + ' + item.vision_model : ' (text + OCR)') : ' · not configured');
    select.append(option);
  }
  select.value = selectedProvider;
  const ready = (data.providers || []).filter(p => p.configured).map(p => p.name);
  const audio = data.audio || {};
  status('Connected.\nProviders ready: ' + (ready.join(', ') || 'none (answers will only quote the marked text)') +
    '\nSpeech: browser voice by default' + (audio.stt && audio.stt.installed ? '; server whisper available in Power mode' : ''), 'ok');
}

$('start').onclick = async () => {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:start-active' });
  if (response && response.ok) window.close(); else status(response && response.error ? response.error : 'Cannot mark this page. Try a normal website or a PDF.', 'err');
};
$('openPdf').onclick = async () => { await chrome.runtime.sendMessage({ type: 'spatial:open-pdf' }); window.close(); };

$('save').onclick = async () => {
  await chrome.storage.local.set({ apiBase: $('apiBase').value.trim().replace(/\/$/, ''), token: $('token').value.trim(),
    voice: $('voice').value.trim(), blocklistExtra: $('blocklistExtra').value.trim() });
  await health($('provider').value);
};
$('privacy').onchange = () => chrome.storage.local.set({ privacy: $('privacy').value });
$('provider').onchange = () => chrome.storage.local.set({ provider: $('provider').value });
$('readAloud').onchange = () => chrome.storage.local.set({ readAloud: $('readAloud').checked });
$('research').onchange = () => chrome.storage.local.set({ research: $('research').checked });
$('pdfViewer').onchange = () => chrome.storage.local.set({ pdfViewer: $('pdfViewer').checked });
$('powerMode').onchange = async () => { await chrome.storage.local.set({ powerMode: $('powerMode').checked }); $('providerLabel').hidden = !(CFG.features.providerPicker || $('powerMode').checked); };

load();
```

- [ ] **Step 7: Geometry alias, docstrings, delete detector**

`extension/geometry.js`: last-but-one line becomes `root.SpatialGeometry = api;`. In the `rankAnchors` comment replace `services/api/app/core/providers.py::resolve_spatial_marks` with `server/app/resolver.py::resolve_marks` and `packages/spatial-core/cases` with `server/tests/cases`.

`server/app/resolver.py` docstring:

```python
"""Deterministic mark resolver: normalizes marks, derives bounding boxes for freehand strokes,
and ranks the DOM/PDF anchors under each mark. Runs before any model call and explains its confidence.
Ranking must stay identical to extension/geometry.js::rankAnchors (see tests/test_resolver_cases.py)."""
```

Also in `resolver.py` replace the comment `# Ranking rule shared with apps/extension/geometry.js (see packages/spatial-core): score desc,` with `# Ranking rule shared with extension/geometry.js (golden cases in tests/cases): score desc,`.

`server/tests/test_resolver_cases.py` docstring first line: `"""Golden resolver cases (tests/cases/*.json).`

Run: `git rm extension/detect.js`

- [ ] **Step 8: Docs**

`README.md`: delete the whole `## Origin and sync` section (to end of file). `docs/PRD.md` line "Spatial is an **independent product** (StudyOS coupling is being removed)." → "Spatial is an **independent, standalone product**." `docs/SPATIAL_PRODUCTION_CHECKLIST.md` and `docs/LEARNING_PATH.md`: rewrite each line matched by `grep -n -i -E "studyos|sync_spatial|quiz|learning-platform"` to drop the StudyOS reference (e.g. LEARNING_PATH item 7 "Spaced-repetition: turn each ask into a flashcard" → "Flashcards: turn each ask into a review card"; any "Quiz button" checklist line → delete).

- [ ] **Step 9: Run tests**

Run (from `server/`): `python -m pytest -q` → all pass (35).
Run (repo root): `node --test extension/tests/geometry.test.mjs` → pass.

- [ ] **Step 10: Commit**

```bash
git add -A extension server/app/resolver.py server/tests README.md docs/SPATIAL_PRODUCTION_CHECKLIST.md docs/LEARNING_PATH.md docs/PRD.md
git commit -m "refactor: remove StudyOS coupling; Spatial is standalone"
```

---

### Task 2: Contract models, v2 conversion and resolver adapter

**Files:**
- Create: `server/app/contracts.py`
- Test: `server/tests/test_contracts.py`

**Interfaces:**
- Consumes: `app.resolver.resolve_marks(marks, canvas, anchors) -> dict` (unchanged).
- Produces (used by Tasks 3-7):
  - Models `BBox`, `SpatialMark`, `Provenance`, `CandidateObject`, `Viewport`, `Surface`, `CropInfo`, `SpatialContext`, `Alternative`, `SemanticResolution`.
  - `from_v2(*, question: str, marks: list[dict], anchors: list[dict], canvas: dict | None, page: dict, privacy_policy: str, crop: CropInfo | None = None) -> SpatialContext` — raises `ValueError("no usable marks")`.
  - `resolver_inputs(ctx) -> tuple[list[dict], dict, list[dict]]` → `(marks, canvas, anchors)` for `resolve_marks`.
  - `candidate_to_anchor(c: CandidateObject) -> dict`, `mark_to_v2(m: SpatialMark) -> dict`, `page_dict(ctx) -> dict`.
  - `to_semantic_resolution(resolution: dict) -> SemanticResolution`.
  - `schema_document() -> dict`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_contracts.py`:

```python
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.contracts import (CropInfo, SpatialContext, candidate_to_anchor, from_v2, mark_to_v2,  # noqa: E402
                           page_dict, resolver_inputs, to_semantic_resolution)
from app.resolver import resolve_marks  # noqa: E402

PAGE = {"url": "https://example.org", "title": "Example", "surface": "web"}
ANCHORS = [
    {"id": "a1", "type": "p", "text": "Pectoralis major", "bbox": {"x": 90, "y": 90, "width": 220, "height": 120}},
    {"id": "a2", "type": "p", "text": "Footer", "bbox": {"x": 0, "y": 600, "width": 500, "height": 40}},
]


def v2(marks, anchors=ANCHORS, page=PAGE, privacy="crop_only"):
    return from_v2(question="What is this?", marks=marks, anchors=anchors, canvas={"width": 1280, "height": 720},
                   page=page, privacy_policy=privacy)


def test_rectangle_and_dom_anchor_convert():
    ctx = v2([{"type": "rectangle", "role": "source", "x": 100, "y": 100, "width": 200, "height": 100}])
    assert ctx.marks[0].kind == "rectangle" and ctx.marks[0].role == "source"
    assert ctx.marks[0].bbox.width == 200
    assert [c.source for c in ctx.candidates] == ["dom", "dom"]
    assert ctx.candidates[0].candidate_id == "a1" and ctx.candidates[0].object_type == "p"
    assert ctx.surface.viewport.width == 1280 and ctx.surface.kind == "web"


def test_pdf_surface_and_page_anchor_become_pdf_text():
    anchors = [{"id": "p", "type": "pdf-text", "page": 2, "text": "Abstract", "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}}]
    ctx = v2([{"type": "circle", "x": 0, "y": 0, "width": 10, "height": 10}], anchors=anchors,
             page={**PAGE, "surface": "pdf"})
    assert ctx.surface.kind == "pdf" and ctx.candidates[0].source == "pdf_text" and ctx.candidates[0].page == 2


def test_polygon_without_bbox_derives_it_from_points():
    ctx = v2([{"type": "polygon", "points": [[10, 20], [110, 20], [110, 80], [10, 80]]}])
    box = ctx.marks[0].bbox
    assert (box.x, box.y, box.width, box.height) == (10, 20, 100, 60)
    assert ctx.marks[0].points[0] == (10, 20)


def test_unknown_marks_and_bad_anchors_are_dropped():
    ctx = v2([{"type": "scribble", "x": 1, "y": 1}, {"type": "point", "x": 5, "y": 5}],
             anchors=[{"id": "x"}, {"type": "p", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}, *ANCHORS])
    assert [m.kind for m in ctx.marks] == ["point"]
    assert [c.candidate_id for c in ctx.candidates] == ["a1", "a2"]
    with pytest.raises(ValueError):
        v2([{"type": "scribble"}])


def test_negative_anchor_coordinates_are_accepted():
    ctx = v2([{"type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50}],
             anchors=[{"id": "off", "type": "div", "text": "t", "bbox": {"x": -40, "y": -10, "width": 100, "height": 30}}])
    assert ctx.candidates[0].bbox.x == -40


def test_unknown_privacy_policy_fails_safe():
    assert v2([{"type": "point", "x": 1, "y": 1}], privacy="whatever").privacy_policy == "anchors_only"


def test_point_mark_without_size_resolves_like_v2():
    raw = [{"type": "point", "role": "reference", "x": 150, "y": 150}]
    ctx = v2(raw)
    marks, canvas, anchors = resolver_inputs(ctx)
    assert "width" not in marks[0] and "height" not in marks[0]
    assert resolve_marks(marks, canvas, anchors)["confidence"] == resolve_marks(raw, {"width": 1280, "height": 720}, ANCHORS)["confidence"]


def test_resolver_adapter_matches_direct_v2_resolution():
    raw = [{"type": "rectangle", "role": "reference", "x": 100, "y": 100, "width": 200, "height": 100}]
    direct = resolve_marks(raw, {"width": 1280, "height": 720}, ANCHORS)
    via = resolve_marks(*resolver_inputs(v2(raw)))
    assert via["candidates"][0]["anchors_ranked"] == direct["candidates"][0]["anchors_ranked"]
    assert via["confidence"] == direct["confidence"]


def test_candidate_to_anchor_and_mark_round_trip():
    ctx = v2([{"type": "polygon", "role": "target", "closed": True, "points": [[0, 0], [10, 0], [10, 10]],
               "x": 0, "y": 0, "width": 10, "height": 10}])
    assert mark_to_v2(ctx.marks[0]) == {"type": "polygon", "role": "target", "x": 0.0, "y": 0.0, "width": 10.0,
                                         "height": 10.0, "points": [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]], "closed": True}
    anchor = candidate_to_anchor(ctx.candidates[0])
    assert anchor["id"] == "a1" and anchor["bbox"] == {"x": 90.0, "y": 90.0, "width": 220.0, "height": 120.0}
    assert anchor["source"] == "dom"
    assert page_dict(ctx) == {"url": "https://example.org", "title": "Example", "surface": "web"}


def test_semantic_resolution_from_resolver_output():
    res = to_semantic_resolution(resolve_marks(*resolver_inputs(v2([{"type": "rectangle", "x": 100, "y": 100, "width": 200, "height": 100}]))))
    assert res.selected_candidate_id == "a1" and res.alternatives[0].candidate_id == "a1"
    assert res.semantic_confidence is None and res.abstained is False
    assert res.resolver == "structured-anchor-v1"


def test_v3_context_validation():
    ok = SpatialContext.model_validate({
        "surface": {"kind": "desktop", "app": "Code", "viewport": {"width": 1920, "height": 1080}},
        "marks": [{"kind": "rectangle", "bbox": {"x": 1, "y": 1, "width": 5, "height": 5}}],
        "candidates": [{"candidate_id": "u1", "source": "uia", "text": "Run", "bbox": {"x": 0, "y": 0, "width": 9, "height": 9},
                        "provenance": {"extractor": "uia"}}],
        "question": "what does this do?",
        "crop": {"bbox": {"x": 0, "y": 0, "width": 100, "height": 50}, "scale": 2},
    })
    assert ok.candidates[0].source == "uia" and isinstance(ok.crop, CropInfo)
    with pytest.raises(ValidationError):
        SpatialContext.model_validate({"surface": {"viewport": {"width": 1, "height": 1}}, "marks": [], "question": "x"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_contracts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.contracts'`.

- [ ] **Step 3: Implement `server/app/contracts.py`**

```python
"""Client-agnostic Spatial contract (protocol v3). Every client — browser extension, desktop app — describes an
ask as a SpatialContext; the server never branches on which client sent it. Also converts the v2 extension payload
and adapts contexts to the deterministic resolver (whose scoring must stay identical to extension/geometry.js)."""
from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, Field
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
    semantic_confidence: float | None = None  # filled by the System-One resolver (sub-project 2)
    confidence: float
    abstained: bool
    resolver: str
    latency_ms: int


# --- v2 (browser extension) -> v3 ----------------------------------------------------------------------------

def _mark_from_v2(raw: Any) -> SpatialMark | None:
    if not isinstance(raw, dict) or raw.get("type") not in _KINDS:
        return None
    try:
        points = raw.get("points")
        pts = [(float(p[0]), float(p[1])) for p in points][:2000] if isinstance(points, list) and points else None
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
    return SpatialMark(mark_id=str(raw["id"]) if raw.get("id") else None, kind=raw["type"],
                       role=raw.get("role") if raw.get("role") in _ROLES else "reference", bbox=box, points=pts,
                       closed=raw["closed"] if isinstance(raw.get("closed"), bool) else None)


def _candidate_from_v2(raw: Any, surface_kind: str) -> CandidateObject | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    box = raw.get("bbox") or raw.get("rect")
    if not isinstance(box, dict):
        return None
    try:
        bbox = BBox(x=float(box.get("x", 0)), y=float(box.get("y", 0)),
                    width=max(0.0, float(box.get("width", 0))), height=max(0.0, float(box.get("height", 0))))
    except (TypeError, ValueError):
        return None
    kind = str(raw.get("type", "unknown"))
    page = raw.get("page")
    page = int(page) if isinstance(page, (int, float)) and not isinstance(page, bool) else None
    if kind == "ocr":
        source = "ocr"
    elif surface_kind == "pdf" or page is not None:
        source = "pdf_text"
    else:
        source = "dom"
    return CandidateObject(candidate_id=str(raw["id"])[:200], source=source, object_type=kind,
                           text=str(raw.get("text") or "")[:1500], bbox=bbox, page=page,
                           href=str(raw["href"])[:500] if raw.get("href") else None,
                           src=str(raw["src"])[:500] if raw.get("src") else None,
                           provenance=Provenance(extractor="extension-v2"))


def from_v2(*, question: str, marks: list[dict], anchors: list[dict], canvas: dict | None, page: dict,
            privacy_policy: str, crop: CropInfo | None = None) -> SpatialContext:
    surface_kind = page.get("surface") if page.get("surface") in _SURFACES else "web"
    converted = [m for m in (_mark_from_v2(raw) for raw in marks) if m is not None][:8]
    if not converted:
        raise ValueError("no usable marks")
    candidates = [c for c in (_candidate_from_v2(raw, surface_kind) for raw in anchors) if c is not None][:200]
    canvas = canvas or {}
    viewport = {"width": max(float(canvas.get("width") or 1), 1.0), "height": max(float(canvas.get("height") or 1), 1.0)}
    return SpatialContext(
        surface=Surface(kind=surface_kind, url=str(page.get("url") or "")[:2000], title=str(page.get("title") or "")[:500],
                        viewport=viewport),
        marks=converted, candidates=candidates, question=question,
        privacy_policy=privacy_policy if privacy_policy in _POLICIES else "anchors_only", crop=crop)


# --- adapters to the deterministic resolver and the answer layer --------------------------------------------

def mark_to_v2(mark: SpatialMark) -> dict:
    out: dict[str, Any] = {"type": mark.kind, "role": mark.role, "x": mark.bbox.x, "y": mark.bbox.y}
    # A v2 point arrives without a size and must not trip the resolver's zero-size penalty.
    if mark.kind != "point" or mark.bbox.width or mark.bbox.height:
        out.update(width=mark.bbox.width, height=mark.bbox.height)
    if mark.points:
        out["points"] = [[x, y] for x, y in mark.points]
    if mark.closed is not None:
        out["closed"] = mark.closed
    return out


def candidate_to_anchor(candidate: CandidateObject) -> dict:
    return {"id": candidate.candidate_id, "type": candidate.object_type or candidate.source, "text": candidate.text,
            "bbox": candidate.bbox.model_dump(), "page": candidate.page, "href": candidate.href or "",
            "src": candidate.src or "", "source": candidate.source}


def resolver_inputs(ctx: SpatialContext) -> tuple[list[dict], dict, list[dict]]:
    return ([mark_to_v2(m) for m in ctx.marks],
            {"width": ctx.surface.viewport.width, "height": ctx.surface.viewport.height},
            [candidate_to_anchor(c) for c in ctx.candidates])


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
                alternatives.append(Alternative(candidate_id=ranked["id"], score=ranked["score"]))
    first = (resolution.get("candidates") or [{}])[0]
    confidence = float(resolution.get("confidence", 0.0))
    return SemanticResolution(selected_candidate_id=first.get("anchor_id"), alternatives=alternatives,
                              geometric_confidence=confidence, confidence=confidence, abstained=confidence < 0.6,
                              resolver=str(resolution.get("resolver", "deterministic-v1")),
                              latency_ms=int(resolution.get("latency_ms", 0)))


def schema_document() -> dict:
    """JSON Schema shared with the JS and Rust clients (written by scripts/export_schema.py)."""
    _, schema = models_json_schema([(SpatialContext, "validation"), (SemanticResolution, "serialization")],
                                   title="Spatial protocol v3")
    return schema
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_contracts.py -v` → all PASS. Then `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add server/app/contracts.py server/tests/test_contracts.py
git commit -m "feat(server): SpatialContext contract, v2 conversion and resolver adapter"
```

---

### Task 3: Protocol v3 in the ask routes

**Files:**
- Modify: `server/app/main.py`
- Test: `server/tests/test_protocol.py` (new), `server/tests/test_server.py:111-116`

**Interfaces:**
- Consumes: Task 2 (`from_v2`, `resolver_inputs`, `candidate_to_anchor`, `mark_to_v2`, `page_dict`, `to_semantic_resolution`, `SpatialContext`, `CropInfo`).
- Produces: `prepare_ask(payload) -> dict` with keys `context` (SpatialContext), `anchors` (list[dict]), `image_data`, `resolution`, `used`, `history`, `sources`, `started`, `timings` (dict[str, int]), `request_id` (str), `ocr_text` (str | None). `finish_ask(payload, prep, text, meta)` response gains `resolution_v3`. Constants `PROTOCOL_VERSION = 3`, `MIN_PROTOCOL_VERSION = 2`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_protocol.py`:

```python
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
        "surface": {"kind": "web", "url": "https://example.org/anatomy", "title": "Anatomy atlas",
                    "viewport": {"width": 1280, "height": 720}},
        "marks": [{"kind": "polygon", "role": "reference", "bbox": {"x": 100, "y": 100, "width": 200, "height": 100},
                   "points": [[100, 100], [300, 100], [300, 200], [100, 200]]}],
        "candidates": [
            {"candidate_id": "a1", "source": "dom", "object_type": "img", "text": "Pectoralis major",
             "bbox": {"x": 90, "y": 90, "width": 220, "height": 120}, "provenance": {"extractor": "test"}},
            {"candidate_id": "a2", "source": "dom", "object_type": "p", "text": "Unrelated footer",
             "bbox": {"x": 0, "y": 600, "width": 500, "height": 40}, "provenance": {"extractor": "test"}},
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
    assert a["resolution_v3"]["selected_candidate_id"] == b["resolution_v3"]["selected_candidate_id"] == "a1"
    assert b["page"] == {"url": "https://example.org/anatomy", "title": "Anatomy atlas", "surface": "web"}
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
        body = client.post("/api/ask", json={**PAYLOAD, "privacy_policy": "weird", "image_data": "data:image/jpeg;base64,AAAA"}).json()
    assert body["resolution"]["image_attached"] is False
```

In `server/tests/test_server.py::test_stream_emits_status_and_complete` change `'"protocol_version": 2'` to `'"protocol_version": 3'`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_protocol.py tests/test_server.py -v`
Expected: FAIL — `KeyError: 'resolution_v3'`, 422 detail is a list, etc.

- [ ] **Step 3: Update imports, constants and the `Ask` model in `main.py`**

Add to imports:

```python
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.contracts import (CropInfo, SpatialContext, from_v2, mark_to_v2, page_dict, resolver_inputs,
                           to_semantic_resolution)
```

Replace `PROTOCOL_VERSION = 2 …` with:

```python
PROTOCOL_VERSION = 3  # v3: SpatialContext payload; bump when the ask payload/response shape changes incompatibly
MIN_PROTOCOL_VERSION = 2  # the v2 browser extension payload is still accepted and converted
```

Replace the `Ask` model:

```python
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
    protocol_version: int = PROTOCOL_VERSION
    client_version: str | None = Field(default=None, max_length=40)
    research: bool = False  # ground the answer in web sources (app/research.py) and cite them
    level: str | None = Field(default=None, max_length=10)  # eli5 | student | expert
```

After the `app.add_middleware(...)` block add the validation handler:

```python
@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Keep the {code, message} error shape clients already handle."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    code = "BAD_CONTEXT" if any("context" in map(str, e.get("loc", ())) for e in errors) else "BAD_REQUEST"
    where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    return JSONResponse(status_code=422, content={"detail": {"code": code, "message": f"{where}: {first.get('msg', 'invalid request')}"}})
```

- [ ] **Step 4: Replace `check_protocol`, add `to_context`, rewrite `prepare_ask` / `finish_ask`**

```python
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
            raise HTTPException(422, {"code": "BAD_CONTEXT", "message": "protocol 3 requires `context`"})
        return payload.context
    if not payload.marks:
        raise HTTPException(400, {"code": "NO_MARKS", "message": "at least one mark is required"})
    if not payload.question:
        raise HTTPException(422, {"code": "BAD_CONTEXT", "message": "question is required"})
    try:
        return from_v2(question=payload.question, marks=payload.marks, anchors=payload.anchors, canvas=payload.canvas,
                       page=payload.page.model_dump(), privacy_policy=payload.privacy_policy, crop=payload.crop)
    except ValueError:
        raise HTTPException(400, {"code": "NO_MARKS", "message": "no usable marks"}) from None


def prepare_ask(payload: Ask) -> dict:
    """Shared front half of ask/ask-stream: validation, contract, resolver, anchors, history, research."""
    started = perf_counter()
    check_protocol(payload)
    ctx = to_context(payload)
    previous = store.get(payload.context_id) if payload.context_id else None
    if payload.context_id and not previous:
        raise HTTPException(404, {"code": "CONTEXT_NOT_FOUND", "message": "context not found"})
    image_data = payload.image_data if ctx.privacy_policy in {"crop_only", "full_frame"} else None
    timings: dict[str, int] = {}
    marks, canvas, anchors = resolver_inputs(ctx)
    resolution = resolve_marks(marks, canvas, anchors)
    timings["resolve"] = resolution["latency_ms"]
    resolution.update({"surface": ctx.surface.kind, "privacy_policy": ctx.privacy_policy, "image_attached": bool(image_data)})
    used = anchors_used(resolution, anchors)
    history = (previous or {}).get("answer", {}).get("history", [])
    research_started = perf_counter()
    sources = research.gather(ctx.question, used) if payload.research else []
    timings["research"] = round((perf_counter() - research_started) * 1000)
    return {"context": ctx, "anchors": anchors, "previous": previous, "image_data": image_data,
            "resolution": resolution, "used": used, "history": history, "sources": sources,
            "started": started, "timings": timings, "request_id": str(uuid4()), "ocr_text": None}
```

In `finish_ask`, use the context instead of the raw payload:

```python
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
    record = {"text": text, "history": history, "anchors_used": prep["used"], "sources": prep["sources"], "meta": meta}
    if prep["previous"]:
        store.update(prep["previous"]["id"], prep["resolution"], record)
        context_id = prep["previous"]["id"]
    else:
        context_id = store.create(page, ctx.question, [mark_to_v2(m) for m in ctx.marks], prep["resolution"], record)
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
```

In both `ask()` and `ask_stream()` change the `answer_stream(...)` call arguments `payload.question` → `prep["context"].question` and `payload.page.model_dump()` → `page_dict(prep["context"])`. Delete the old `if not payload.marks: raise … NO_MARKS` block (now in `to_context`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q` → all pass (including `test_outdated_client_rejected`, protocol 1 → 426).

- [ ] **Step 6: Commit**

```bash
git add server/app/main.py server/tests/test_protocol.py server/tests/test_server.py
git commit -m "feat(server): protocol v3 SpatialContext payload; v2 converted server-side"
```

---

### Task 4: OCR blocks as candidates

**Files:**
- Modify: `server/app/ocr.py`, `server/app/providers.py` (`answer_stream` signature + OCR bootstrap), `server/app/main.py` (`prepare_ask`, answer calls), `extension/background.js` (`captureCrop`, `spatial:capture`), `extension/content.js` (payload)
- Create: `server/app/candidates.py`
- Test: `server/tests/test_candidates.py`

**Interfaces:**
- Consumes: Task 2 models (`BBox`, `CandidateObject`, `CropInfo`, `Provenance`); Task 3 `prep` dict.
- Produces: `ocr.ocr_blocks(image_data: str | None) -> list[dict]` (`{"text", "bbox": {x,y,width,height}, "confidence"}` in crop px); `candidates.ocr_candidates(blocks, crop) -> list[CandidateObject]`; `candidates.merge(candidates) -> list[CandidateObject]`; `providers.answer_stream(..., precomputed_ocr: str | None = None)`; `prep["ocr_text"]`; `prep["timings"]["ocr"]`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_candidates.py`:

```python
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
    {"text": "Revenue by quarter", "bbox": {"x": 20, "y": 10, "width": 200, "height": 30}, "confidence": 0.93},
    {"text": "Pectoralis major", "bbox": {"x": 40, "y": 60, "width": 160, "height": 20}, "confidence": 0.9},
]


def cand(cid, source, text, x, y, w, h):
    return CandidateObject(candidate_id=cid, source=source, text=text, bbox=BBox(x=x, y=y, width=w, height=h),
                           provenance=Provenance(extractor="t"))


def test_ocr_boxes_map_from_crop_to_surface_coordinates():
    crop = CropInfo(bbox=BBox(x=100, y=50, width=400, height=200), scale=2.0)
    out = candidates.ocr_candidates(BLOCKS, crop)
    assert [c.candidate_id for c in out] == ["ocr-0", "ocr-1"]
    assert out[0].source == "ocr" and out[0].bbox == BBox(x=110, y=55, width=100, height=15)
    assert out[0].attributes["confidence"] == "0.93"


def test_no_crop_means_no_ocr_candidates():
    assert candidates.ocr_candidates(BLOCKS, None) == []


def test_merge_drops_ocr_duplicating_structured_text_and_keeps_unique():
    dom = cand("a1", "dom", "The Pectoralis major muscle", 100, 100, 300, 60)
    dup = cand("ocr-1", "ocr", "pectoralis  MAJOR", 120, 110, 150, 20)      # inside a1, text contained
    unique = cand("ocr-0", "ocr", "Revenue by quarter", 600, 100, 200, 30)
    far_dup_text = cand("ocr-2", "ocr", "Pectoralis major", 900, 600, 150, 20)  # same words, elsewhere: keep
    merged = candidates.merge([dom, dup, unique, far_dup_text])
    assert [c.candidate_id for c in merged] == ["a1", "ocr-0", "ocr-2"]


def test_merge_caps_candidates():
    many = [cand(f"c{i}", "dom", f"t{i}", i, 0, 1, 1) for i in range(100)]
    assert len(candidates.merge(many)) == 64


def test_ask_uses_ocr_candidates_when_crop_given(monkeypatch):
    monkeypatch.setattr(main.settings, "ocr_enabled", True)
    monkeypatch.setattr(main, "ocr_blocks", lambda image: BLOCKS)
    body = {**PAYLOAD, "anchors": [], "image_data": "data:image/jpeg;base64,AAAA",
            "crop": {"bbox": {"x": 80, "y": 80, "width": 260, "height": 140}, "scale": 1.0}}
    with TestClient(main.app) as client:
        result = client.post("/api/ask", json=body).json()
    assert result["anchors_used"][0]["id"].startswith("ocr-")
    assert result["anchors_used"][0]["type"] == "ocr"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_candidates.py -v`
Expected: FAIL — `ImportError: cannot import name 'candidates'`.

- [ ] **Step 3: `server/app/ocr.py` — blocks with boxes**

Replace `ocr_image` with:

```python
def ocr_blocks(image_data: str | None) -> list[dict]:
    """Text blocks with boxes in crop px: [{text, bbox: {x, y, width, height}, confidence}], reading order as given."""
    if not image_data:
        return []
    engine = _engine()
    if engine is None:
        return []
    try:
        from PIL import Image
        import numpy as np
        raw = base64.b64decode(image_data.split(",", 1)[-1])
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        result, _ = engine(np.array(image))
        blocks = []
        # RapidOCR returns [box (4 corner points), text, score].
        for item in result or []:
            if len(item) < 3:
                continue
            text, score = str(item[1]).strip(), float(item[2])
            if not text or score < 0.4:
                continue
            xs, ys = [float(p[0]) for p in item[0]], [float(p[1]) for p in item[0]]
            blocks.append({"text": text, "confidence": round(score, 3),
                           "bbox": {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}})
        return blocks
    except Exception:
        return []


def ocr_image(image_data: str | None) -> str:
    return "\n".join(block["text"] for block in ocr_blocks(image_data)).strip()
```

- [ ] **Step 4: Create `server/app/candidates.py`**

```python
"""Candidate sources beyond what the client collected: OCR blocks from the attached crop, merged with
structured candidates (DOM / PDF text / UIA win over OCR when they describe the same thing)."""
from __future__ import annotations

from app.contracts import BBox, CandidateObject, CropInfo, Provenance

STRUCTURED = {"dom", "pdf_text", "uia"}
MAX_CANDIDATES = 64


def ocr_candidates(blocks: list[dict], crop: CropInfo | None) -> list[CandidateObject]:
    """Map OCR boxes from crop px to surface px. Without crop geometry the boxes cannot be placed: no candidates."""
    if crop is None:
        return []
    out = []
    for index, block in enumerate(blocks):
        box, scale = block["bbox"], crop.scale
        out.append(CandidateObject(
            candidate_id=f"ocr-{index}", source="ocr", object_type="ocr", text=str(block["text"])[:1500],
            bbox=BBox(x=crop.bbox.x + box["x"] / scale, y=crop.bbox.y + box["y"] / scale,
                      width=box["width"] / scale, height=box["height"] / scale),
            attributes={"confidence": str(block.get("confidence", ""))},
            provenance=Provenance(extractor="rapidocr", extractor_version="1")))
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
            _inside_fraction(candidate.bbox, other.bbox) >= 0.8 and _norm(candidate.text) in _norm(other.text)
            for other in structured
        ):
            continue
        kept.append(candidate)
    return kept[:MAX_CANDIDATES]
```

- [ ] **Step 5: `providers.answer_stream` accepts precomputed OCR**

Add parameter `precomputed_ocr: str | None = None,` after `level: str | None = None,` in the signature, and replace

```python
    ocr_text = ""
    ocr_tried = False
```

with

```python
    ocr_text = precomputed_ocr or ""
    ocr_tried = precomputed_ocr is not None  # the server already ran OCR to build candidates
```

- [ ] **Step 6: `main.prepare_ask` runs OCR once and merges candidates**

Imports: `from app.candidates import merge, ocr_candidates` and `from app.ocr import ocr_blocks`.
In `prepare_ask`, right after the `image_data = …` line insert:

```python
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
```

remove the later duplicate `timings: dict[str, int] = {}` line, and return `"ocr_text": ocr_text` instead of `None`. In both `answer_stream(...)` calls add `precomputed_ocr=prep["ocr_text"],` as the last keyword argument.

- [ ] **Step 7: Extension sends crop geometry**

`extension/background.js` — `captureCrop` returns `{ image, crop }` (crop in CSS px, scale = image px per CSS px):

```js
async function captureCrop(windowId, box, dpr, mode) {
  const dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: 'png' });
  const blob = await (await fetch(dataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  if (mode === 'full_frame') return { image: dataUrl, crop: { bbox: { x: 0, y: 0, width: bitmap.width / dpr, height: bitmap.height / dpr }, scale: dpr } };
  const pad = 28 * dpr;
  const sx = Math.max(0, Math.floor(box.x * dpr - pad)), sy = Math.max(0, Math.floor(box.y * dpr - pad));
  const sw = Math.min(bitmap.width - sx, Math.ceil(box.width * dpr + pad * 2)), sh = Math.min(bitmap.height - sy, Math.ceil(box.height * dpr + pad * 2));
  if (sw <= 0 || sh <= 0) return { image: null, crop: null };
  const scale = Math.min(1, 1600 / Math.max(sw, sh));
  const canvas = new OffscreenCanvas(Math.round(sw * scale), Math.round(sh * scale));
  canvas.getContext('2d').drawImage(bitmap, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  const out = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.86 });
  const image = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsDataURL(out); });
  return { image, crop: { bbox: { x: sx / dpr, y: sy / dpr, width: sw / dpr, height: sh / dpr }, scale: scale * dpr } };
}
```

and the `spatial:capture` case:

```js
        case 'spatial:capture': {
          if (config.privacy === 'anchors_only') return sendResponse({ ok: true, image: null, crop: null });
          const { image, crop } = await captureCrop(sender.tab.windowId, message.box, message.dpr || 1, config.privacy);
          return sendResponse({ ok: true, image, crop });
        }
```

`extension/content.js` payload — after `image_data: capture.ok ? capture.image : null,` add:

```js
        crop: capture.ok ? capture.crop : null,
```

- [ ] **Step 8: Run tests**

Run: `python -m pytest -q` → all pass. `node --test extension/tests/geometry.test.mjs` → pass.

- [ ] **Step 9: Commit**

```bash
git add server/app/ocr.py server/app/candidates.py server/app/providers.py server/app/main.py server/tests/test_candidates.py extension/background.js extension/content.js
git commit -m "feat: OCR blocks become placed candidates; extension sends crop geometry"
```

---

### Task 5: Opt-in trace log

**Files:**
- Create: `server/app/trace.py`
- Modify: `server/app/config.py`, `server/app/main.py`, `server/.env.example`, `extension/config.js`, `extension/background.js`, `extension/popup.html`, `extension/popup.js`
- Test: `server/tests/test_trace.py`

**Interfaces:**
- Consumes: Task 2 models; Task 3 `prep` (`context`, `request_id`, `timings`, `image_data`, `started`).
- Produces: `trace.enabled() -> bool`, `trace.set_enabled(value: bool) -> None`, `trace.build_record(*, request_id, context_id, client, ctx, image_attached, resolution, answer, meta, timings) -> dict`, `trace.write(record: dict) -> None`, `trace.export() -> Iterator[bytes]`, `trace.delete_all() -> int`, `trace.status() -> dict`, `trace.log_dir() -> Path`. Routes `GET/PUT /api/traces/config`, `GET /api/traces/export`, `DELETE /api/traces`; health key `trace`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_trace.py`:

```python
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("SPATIAL_DB", str(Path(__file__).parent / "test_spatial.db"))
os.environ.setdefault("SPATIAL_PROVIDERS", "nothing")
os.environ.setdefault("SPATIAL_OCR", "0")
os.environ.setdefault("SPATIAL_API_TOKEN", "")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main, trace  # noqa: E402
from tests.test_server import PAYLOAD  # noqa: E402

BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{200,}")


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(trace.settings, "trace_dir", str(tmp_path))
    monkeypatch.setattr(trace.settings, "trace_enabled", False)
    monkeypatch.setattr(trace.settings, "trace_max_mb", 50.0)
    monkeypatch.setattr(trace.settings, "trace_retention_days", 14)
    trace._state["error"] = None
    return tmp_path


def lines(directory: Path) -> list[dict]:
    return [json.loads(line) for f in sorted(directory.glob("*.jsonl")) for line in f.read_text(encoding="utf-8").splitlines()]


def test_off_by_default_writes_nothing(log_dir):
    with TestClient(main.app) as client:
        client.post("/api/ask", json=PAYLOAD)
    assert list(log_dir.glob("*.jsonl")) == []


def test_on_writes_one_line_per_ask_without_images(log_dir):
    image = "data:image/jpeg;base64," + "A" * 5000
    anchors = [*PAYLOAD["anchors"], {"id": "inline", "type": "img", "text": "", "src": "data:image/png;base64," + "B" * 400,
                                      "bbox": {"x": 95, "y": 95, "width": 50, "height": 50}}]
    with TestClient(main.app) as client:
        assert client.put("/api/traces/config", json={"enabled": True}).json()["enabled"] is True
        client.post("/api/ask", json={**PAYLOAD, "anchors": anchors, "image_data": image})
        client.post("/api/ask", json=PAYLOAD)
    records = lines(log_dir)
    assert len(records) == 2
    first = records[0]
    assert first["trace_version"] == 1 and first["question"] == "What is this?" and first["image_attached"] is True
    assert first["resolution"]["selected_candidate_id"] == "a1"
    assert {"resolve", "research", "answer", "total"} <= set(first["timings_ms"])
    raw = "".join(f.read_text(encoding="utf-8") for f in log_dir.glob("*.jsonl"))
    assert "data:image" not in raw and not BASE64_RUN.search(raw)
    assert "image_data" not in raw


def test_config_persists_in_log_dir(log_dir):
    trace.set_enabled(True)
    assert json.loads((log_dir / "config.json").read_text()) == {"enabled": True}
    assert trace.enabled() is True
    trace.set_enabled(False)
    assert trace.enabled() is False


def test_retention_and_size_cap(log_dir, monkeypatch):
    old = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    mid = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    (log_dir / f"{old}.jsonl").write_text("{}\n")
    (log_dir / f"{mid}.jsonl").write_text("x" * 2_000_000)
    monkeypatch.setattr(trace.settings, "trace_max_mb", 1.0)
    trace.set_enabled(True)
    trace.write({"trace_version": 1})
    names = sorted(p.name for p in log_dir.glob("*.jsonl"))
    assert names == [datetime.now().strftime("%Y-%m-%d") + ".jsonl"]


def test_export_and_delete(log_dir):
    trace.set_enabled(True)
    trace.write({"n": 1})
    with TestClient(main.app) as client:
        exported = client.get("/api/traces/export")
        assert exported.status_code == 200 and json.loads(exported.text.splitlines()[0]) == {"n": 1}
        assert client.delete("/api/traces").json() == {"deleted_files": 1}
    assert list(log_dir.glob("*.jsonl")) == []


def test_unwritable_dir_never_fails_the_ask(log_dir, monkeypatch):
    blocker = log_dir / "blocked"
    blocker.write_text("i am a file, not a directory")
    monkeypatch.setattr(trace.settings, "trace_dir", str(blocker))
    monkeypatch.setattr(trace.settings, "trace_enabled", True)
    with TestClient(main.app) as client:
        assert client.post("/api/ask", json=PAYLOAD).status_code == 200
        health = client.get("/api/health").json()
    assert health["trace"]["enabled"] is False and health["trace"]["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trace.py -v`
Expected: FAIL — `ImportError: cannot import name 'trace'`.

- [ ] **Step 3: Settings in `server/app/config.py`**

Add to `Settings` (after `force_ipv4`):

```python
    # Opt-in local trace log (app/trace.py): metadata + resolution trace per ask, never pixels.
    trace_enabled: bool = (_env("SPATIAL_TRACE") or "off").lower() in {"on", "1", "true", "yes"}
    trace_dir: str | None = _env("SPATIAL_LOG_DIR")
    trace_max_mb: float = float(_env("SPATIAL_TRACE_MAX_MB", "50"))
    trace_retention_days: int = int(_env("SPATIAL_TRACE_RETENTION_DAYS", "14"))
```

Append to `server/.env.example`:

```
# --- Trace log (opt-in; question, answer, what was resolved — never images) ---
SPATIAL_TRACE=off                        # on | off (the extension popup can also toggle it)
SPATIAL_LOG_DIR=                         # default: %APPDATA%\Spatial\logs (Windows)
SPATIAL_TRACE_MAX_MB=50
SPATIAL_TRACE_RETENTION_DAYS=14
```

- [ ] **Step 4: Create `server/app/trace.py`**

```python
"""Opt-in local trace log: one JSON line per ask with the resolution trace (marks, candidates, what was
resolved, question, answer, timings). Separate from the SQLite history, and never contains image bytes:
records are built from an allowlist, and data: URLs are stripped. A broken log directory disables tracing
for the process instead of failing asks."""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings
from app.contracts import SemanticResolution, SpatialContext

TRACE_VERSION = 1
logger = logging.getLogger("spatial.trace")
_lock = threading.Lock()
_state: dict[str, str | None] = {"error": None}


def default_log_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Spatial" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Spatial"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "spatial" / "logs"


def log_dir() -> Path:
    return Path(settings.trace_dir) if settings.trace_dir else default_log_dir()


def _config_path() -> Path:
    return log_dir() / "config.json"


def enabled() -> bool:
    if _state["error"]:
        return False
    try:
        value = json.loads(_config_path().read_text(encoding="utf-8")).get("enabled")
        if isinstance(value, bool):
            return value
    except (OSError, ValueError, AttributeError):
        pass
    return settings.trace_enabled


def set_enabled(value: bool) -> None:
    """Runtime switch (popup toggle), persisted next to the logs. Raises OSError if the directory is unusable."""
    with _lock:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        _config_path().write_text(json.dumps({"enabled": value}), encoding="utf-8")
        _state["error"] = None


def _no_data_url(value: str | None) -> str | None:
    return None if value and value.lstrip().lower().startswith("data:") else value


def build_record(*, request_id: str, context_id: str, client: dict, ctx: SpatialContext, image_attached: bool,
                 resolution: SemanticResolution, answer: str, meta: dict, timings: dict) -> dict[str, Any]:
    candidates = []
    for candidate in ctx.candidates:
        item = candidate.model_dump()
        item["href"], item["src"] = _no_data_url(item["href"]), _no_data_url(item["src"])
        candidates.append(item)
    return {
        "trace_version": TRACE_VERSION,
        "request_id": request_id,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "context_id": context_id,
        "client": client,
        "surface": ctx.surface.model_dump(),
        "privacy_policy": ctx.privacy_policy,
        "image_attached": image_attached,
        "marks": [m.model_dump() for m in ctx.marks],
        "candidates": candidates,
        "resolution": resolution.model_dump(),
        "question": ctx.question,
        "answer": answer,
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "timings_ms": timings,
        "errors": meta.get("errors", {}),
        "cost_usd": meta.get("cost_usd", 0.0),
    }


def _files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.jsonl") if p.is_file())


def _prune(directory: Path) -> None:
    today = datetime.now().date()
    cutoff = today - timedelta(days=settings.trace_retention_days)
    for path in _files(directory):
        try:
            if datetime.strptime(path.stem, "%Y-%m-%d").date() < cutoff:
                path.unlink(missing_ok=True)
        except ValueError:
            continue
    files = _files(directory)
    cap = settings.trace_max_mb * 1024 * 1024
    total = sum(p.stat().st_size for p in files)
    while len(files) > 1 and total > cap:  # oldest first; today's file is always kept
        oldest = files.pop(0)
        total -= oldest.stat().st_size
        oldest.unlink(missing_ok=True)


def write(record: dict[str, Any]) -> None:
    if not enabled():
        return
    try:
        with _lock:
            directory = log_dir()
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            _prune(directory)
    except OSError as exc:
        _state["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("trace log disabled for this process: %s", _state["error"])


def export() -> Iterator[bytes]:
    with _lock:
        paths = _files(log_dir()) if log_dir().is_dir() else []
    for path in paths:
        yield path.read_bytes()


def delete_all() -> int:
    with _lock:
        directory = log_dir()
        paths = _files(directory) if directory.is_dir() else []
        for path in paths:
            path.unlink(missing_ok=True)
    return len(paths)


def status() -> dict[str, Any]:
    directory = log_dir()
    size = sum(p.stat().st_size for p in _files(directory)) if directory.is_dir() else 0
    return {"enabled": enabled(), "dir": str(directory), "size_mb": round(size / 1024 / 1024, 3), "error": _state["error"]}
```

- [ ] **Step 5: Wire into `main.py`**

Imports: `from app import trace`.

In `finish_ask`, compute the v3 resolution once and write the trace before returning. Replace the `"resolution_v3": to_semantic_resolution(resolution).model_dump(),` line by building `semantic = to_semantic_resolution(resolution)` above the `return`, using `"resolution_v3": semantic.model_dump(),`, and assigning the response dict to `response` then:

```python
    if trace.enabled():
        total = round((perf_counter() - prep["started"]) * 1000)
        timings = {**prep["timings"]}
        timings["answer"] = max(0, total - sum(timings.values()))
        timings["total"] = total
        trace.write(trace.build_record(
            request_id=prep["request_id"], context_id=context_id,
            client={"protocol": payload.protocol_version, "version": payload.client_version},
            ctx=prep["context"], image_attached=bool(prep["image_data"]), resolution=semantic,
            answer=text, meta=meta, timings=timings))
    return response
```

Routes (after `delete_context`):

```python
class TraceConfig(BaseModel):
    enabled: bool


@app.get("/api/traces/config", dependencies=[Depends(require_token)])
def get_trace_config():
    return trace.status()


@app.put("/api/traces/config", dependencies=[Depends(require_token)])
def put_trace_config(body: TraceConfig):
    try:
        trace.set_enabled(body.enabled)
    except OSError as exc:
        raise HTTPException(503, {"code": "TRACE_UNAVAILABLE", "message": f"cannot use log directory: {exc}"}) from None
    return trace.status()


@app.get("/api/traces/export", dependencies=[Depends(require_token)])
def export_traces():
    return StreamingResponse(trace.export(), media_type="application/x-ndjson",
                             headers={"Content-Disposition": 'attachment; filename="spatial-traces.jsonl"'})


@app.delete("/api/traces", dependencies=[Depends(require_token)])
def delete_traces():
    return {"deleted_files": trace.delete_all()}
```

In `health()` add `"trace": trace.status(),` to the returned dict.

- [ ] **Step 6: Extension toggle**

`extension/config.js` `paths`: add `traceConfig: '/api/traces/config',`.

`extension/background.js` — add before the message listener:

```js
async function setTrace(enabled) {
  const config = await settings();
  const response = await fetch(apiUrl(config, 'traceConfig'), { method: 'PUT', headers: await headers(config), body: JSON.stringify({ enabled }) });
  if (!response.ok) throw await failure(response);
  return response.json();
}
```

and the case `case 'spatial:trace': return sendResponse({ ok: true, trace: await setTrace(Boolean(message.enabled)) });`.

`extension/popup.html` — after the `powerMode` row:

```html
  <label class="row"><input type="checkbox" id="traceLog"> Keep a local trace log (question, answer, what was resolved; never images)</label>
```

`extension/popup.js` — in `health()` after `const audio = data.audio || {};` add `$('traceLog').checked = Boolean(data.trace && data.trace.enabled);` and at the bottom (before `load();`):

```js
$('traceLog').onchange = async () => {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:trace', enabled: $('traceLog').checked });
  if (!response || !response.ok) { $('traceLog').checked = !$('traceLog').checked; status((response && response.error) || 'Could not change the trace log', 'err'); }
  else status('Trace log ' + (response.trace.enabled ? 'on: ' + response.trace.dir : 'off') + '.', 'ok');
};
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add server/app/trace.py server/app/config.py server/app/main.py server/.env.example server/tests/test_trace.py extension/config.js extension/background.js extension/popup.html extension/popup.js
git commit -m "feat: opt-in local trace log with retention, export and delete; popup toggle"
```

---

### Task 6: JSON Schema export

**Files:**
- Create: `scripts/export_schema.py`, `schema/spatial-context.v3.json` (generated)
- Test: `server/tests/test_schema.py`

**Interfaces:**
- Consumes: `contracts.schema_document() -> dict`.
- Produces: committed `schema/spatial-context.v3.json`.

- [ ] **Step 1: Write the failing test**

`server/tests/test_schema.py`:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.contracts import schema_document  # noqa: E402

SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "spatial-context.v3.json"


def test_committed_schema_matches_models():
    assert SCHEMA.exists(), "run: python scripts/export_schema.py"
    assert json.loads(SCHEMA.read_text(encoding="utf-8")) == schema_document()


def test_schema_covers_contract():
    defs = schema_document()["$defs"]
    assert {"SpatialContext", "CandidateObject", "SpatialMark", "SemanticResolution"} <= set(defs)
    assert defs["CandidateObject"]["properties"]["source"]["enum"] == ["dom", "pdf_text", "ocr", "uia", "vision"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_schema.py -v` → FAIL (`run: python scripts/export_schema.py`).

- [ ] **Step 3: Create `scripts/export_schema.py`**

```python
"""Write schema/spatial-context.v3.json from the pydantic contract (server/app/contracts.py).
Run after changing the contract; tests/test_schema.py fails when the committed file drifts."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from app.contracts import schema_document  # noqa: E402

target = ROOT / "schema" / "spatial-context.v3.json"
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(schema_document(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {target.relative_to(ROOT)}")
```

- [ ] **Step 4: Generate and verify**

Run (repo root): `python scripts/export_schema.py` → `wrote schema/spatial-context.v3.json`.
Run (from `server/`): `python -m pytest tests/test_schema.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/export_schema.py schema/spatial-context.v3.json server/tests/test_schema.py
git commit -m "feat: generated JSON Schema for protocol v3 with drift test"
```

---

### Task 7: Eval cases, evaluation harness and baseline

**Files:**
- Create: `server/tests/eval_cases/generate.py`, `server/tests/eval_cases/*.json` (43, generated), `server/app/evaluation.py`, `scripts/eval.py`, `server/tests/eval_baseline.json` (generated), `server/tests/test_evaluation.py`
- Modify: `server/tests/test_resolver_cases.py` (parity also over eval cases)

**Interfaces:**
- Consumes: Task 2 (`from_v2`, `resolver_inputs`, `SpatialContext`); `resolve_marks`.
- Produces: `evaluation.load_cases(dirs: list[Path]) -> list[dict]` (normalized: `name, category, question, surface, canvas, marks, anchors, intended: list[str] | list[list[str]], ambiguous: bool`); `evaluation.run_case(case) -> dict` (`name, category, top1, top3, abstained, latency_ms, predicted`); `evaluation.summarize(results) -> dict` (`cases, top1, top3, abstain_rate, p50_ms, p95_ms, by_category`); `evaluation.load_traces(directory) -> list[dict]`; `evaluation.run_trace(record) -> dict`.

Case file format (eval cases): `{"description", "category", "question", "surface", "canvas", "marks", "anchors", "intended": [ids], "ambiguous": bool}`. Every mark carries explicit `x/y/width/height` (the client's bbox is the contract, which keeps JS/Python parity exact). Golden cases (`tests/cases`) are normalized on load: `intended = expect["tops"]` (one list entry per mark) or `[expect["top"]]`.

- [ ] **Step 1: Write the case generator**

`server/tests/eval_cases/generate.py`:

```python
"""Deterministic generator for labelled resolver eval cases. `intended` is set by construction (the element
the mark was drawn for), never by running the resolver. Re-run to regenerate:  python tests/eval_cases/generate.py"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

OUT = Path(__file__).parent
W, H = 1280, 720
rng = random.Random(20260923)
LOREM = [
    "Gradient descent updates each weight in the direction that lowers the loss.",
    "The learning rate controls how far each update moves the parameters.",
    "Momentum keeps a running average of past gradients to smooth the path.",
    "Batch normalization rescales activations so training stays stable.",
    "Dropout randomly disables units so the network cannot co-adapt.",
    "The validation loss rises when the model starts to overfit.",
]
EQUATIONS = ["dy/dx = (2x)/2 = x", "L = -Σ y log ŷ", "θ ← θ − η ∇L(θ)", "σ(z) = 1 / (1 + e^{-z})"]
CELLS = ["Q1", "Q2", "Q3", "Q4", "$1.2M", "$1.5M", "$0.9M", "$2.1M", "+12%", "+25%", "-40%", "+133%"]


def box(x, y, w, h):
    return {"x": round(x, 1), "y": round(y, 1), "width": round(w, 1), "height": round(h, 1)}


def anchor(id_, type_, text, b, page=None):
    a = {"id": id_, "type": type_, "text": text, "bbox": b}
    if page is not None:
        a["page"] = page
    return a


def rect_around(b, pad, kind="rectangle", role="reference"):
    return {"type": kind, "role": role, **box(b["x"] - pad, b["y"] - pad, b["width"] + 2 * pad, b["height"] + 2 * pad)}


def circle_stroke(b, slack):
    """Closed freehand circle around b; carries the client's bbox (no padding for closed strokes)."""
    cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    rx, ry = b["width"] / 2 + slack, b["height"] / 2 + slack
    pts = [[round(cx + rx * math.cos(t)), round(cy + ry * math.sin(t))] for t in (i * 2 * math.pi / 40 for i in range(41))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"type": "polygon", "role": "reference", "closed": True, "points": pts,
            **box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))}


def underline_stroke(b):
    """Open stroke under a line of text, padded like geometry.js::strokeToMark (8..40 px, 15% of diagonal)."""
    y = b["y"] + b["height"] + 4
    pts = [[round(b["x"] + i * b["width"] / 10), round(y + (i % 2))] for i in range(11)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    pad = max(8, min(40, math.hypot(w, h) * 0.15))
    return {"type": "polygon", "role": "reference", "closed": False, "points": pts,
            **box(max(0, min(xs) - pad), max(0, min(ys) - pad), w + 2 * pad, h + 2 * pad)}


def case(name, category, description, question, marks, anchors, intended, surface="web", ambiguous=False):
    (OUT / f"{name}.json").write_text(json.dumps({
        "description": description, "category": category, "question": question, "surface": surface,
        "canvas": {"width": W, "height": H}, "marks": marks, "anchors": anchors,
        "intended": intended, "ambiguous": ambiguous}, indent=1) + "\n", encoding="utf-8")


def paragraphs(n, top=80, x=120, w=640, h=52, gap=14):
    return [anchor(f"p{i}", "p", LOREM[i % len(LOREM)], box(x, top + i * (h + gap), w, h)) for i in range(n)]


def web_cases():
    for i in range(5):  # sloppy rectangle around one paragraph in a column
        ps = paragraphs(rng.randint(4, 6))
        k = rng.randrange(len(ps))
        case(f"web_paragraph_{i}", "web", "rectangle around one paragraph, padding 2-14 px, may touch neighbours",
             "explain this", [rect_around(ps[k]["bbox"], rng.randint(2, 14))], ps, [ps[k]["id"]])
    for i in range(4):  # nested: section container + heading + paragraphs + inline link
        sec = box(100, 100, 700, 320)
        head = anchor("h", "h2", "Optimisers", box(120, 115, 300, 36))
        p1 = anchor("p1", "p", LOREM[0] + " See Adam for details.", box(120, 165, 660, 70))
        link = anchor("link", "a", "Adam", box(560, 190, 52, 20))
        p2 = anchor("p2", "p", LOREM[2], box(120, 250, 660, 70))
        section = anchor("section", "section", " ".join(a["text"] for a in (head, p1, p2)), sec)
        items = [section, head, p1, link, p2]
        if i < 2:
            case(f"web_nested_link_{i}", "web", "tight box around an inline link inside a paragraph inside a section",
                 "what is this?", [rect_around(link["bbox"], rng.randint(2, 5))], items, ["link"])
        else:
            case(f"web_nested_section_{i}", "web", "loose circle around a whole section",
                 "summarize this", [circle_stroke(sec, rng.randint(10, 25))], items, ["section"])
    for i in range(3):  # table cell
        cells = [anchor(f"c{r}{c}", "td", CELLS[r * 4 + c], box(150 + c * 140, 200 + r * 44, 140, 44)) for r in range(3) for c in range(4)]
        k = rng.randrange(len(cells))
        case(f"web_table_cell_{i}", "web", "box around one table cell", "why is this negative?",
             [rect_around(cells[k]["bbox"], rng.randint(1, 6))], cells, [cells[k]["id"]])
    for i in range(3):  # point on a button that sits inside a toolbar container
        bar = anchor("toolbar", "div", "File Edit View Run Help", box(0, 0, W, 48))
        buttons = [anchor(f"b{j}", "button", name, box(20 + j * 90, 8, 80, 32)) for j, name in enumerate(["File", "Edit", "View", "Run", "Help"])]
        k = rng.randrange(len(buttons))
        b = buttons[k]["bbox"]
        point = {"type": "point", "role": "reference", "x": b["x"] + b["width"] / 2, "y": b["y"] + b["height"] / 2}
        case(f"web_point_button_{i}", "web", "point mark on a toolbar button (container also contains the point)",
             "what does this do?", [point], [bar, *buttons], [buttons[k]["id"]])


def pdf_cases():
    for i in range(6):  # merged block + glyph fragments
        blocks = [anchor(f"pdf-{i}-{j}", "pdf-text", LOREM[(i + j) % len(LOREM)], box(140, 120 + j * 110, 620, 90), page=i + 1) for j in range(4)]
        k = rng.randrange(len(blocks))
        tb = blocks[k]["bbox"]
        frags = [anchor(f"frag-{j}", "span", LOREM[(i + k) % len(LOREM)].split()[j], box(tb["x"] + 10 + j * 70, tb["y"] + 8, 60, 18), page=i + 1) for j in range(3)]
        case(f"pdf_block_{i}", "pdf", "sloppy circle around one merged PDF block; glyph spans inside it",
             "explain this paragraph", [circle_stroke(tb, rng.randint(4, 30))], blocks + frags, [blocks[k]["id"]], surface="pdf")
    for i in range(3):  # equation line among text lines
        lines = [anchor(f"l{j}", "pdf-text", LOREM[j], box(140, 150 + j * 40, 620, 28), page=3) for j in range(5)]
        eq = anchor("eq", "pdf-text", EQUATIONS[i], box(300, 150 + 5 * 40, 260, 30), page=3)
        case(f"pdf_equation_{i}", "pdf", "tight circle around an equation line", "why this step?",
             [circle_stroke(eq["bbox"], rng.randint(3, 10))], [*lines, eq], ["eq"], surface="pdf")
    for i in range(3):  # underline
        lines = [anchor(f"l{j}", "pdf-text", LOREM[(i + j) % len(LOREM)], box(140, 150 + j * 34, 620, 24), page=2) for j in range(6)]
        k = rng.randrange(1, 5)
        case(f"pdf_underline_{i}", "pdf", "open stroke drawn under one line of text", "what does this mean?",
             [underline_stroke(lines[k]["bbox"])], lines, [lines[k]["id"]], surface="pdf")


def ambiguous_cases():
    for i in range(4):  # straddle two paragraphs equally
        ps = paragraphs(4)
        k = rng.randrange(3)
        a, b = ps[k]["bbox"], ps[k + 1]["bbox"]
        mid = a["y"] + a["height"] + 7
        mark = {"type": "rectangle", "role": "reference", **box(a["x"] + 40, mid - 40, 400, 80)}
        case(f"ambiguous_between_{i}", "ambiguous", "box straddling two paragraphs equally", "explain this",
             [mark], ps, [ps[k]["id"], ps[k + 1]["id"]], ambiguous=True)
    for i in range(2):  # two table cells
        cells = [anchor(f"c{c}", "td", CELLS[c + 4], box(150 + c * 140, 240, 140, 44)) for c in range(4)]
        k = rng.randrange(3)
        mark = {"type": "rectangle", "role": "reference", **box(150 + k * 140 + 70, 244, 140, 36)}
        case(f"ambiguous_cells_{i}", "ambiguous", "box half over two adjacent cells", "why is this higher?",
             [mark], cells, [cells[k]["id"], cells[k + 1]["id"]], ambiguous=True)
    for i in range(2):  # image + caption
        img = anchor("img", "img", "Loss curve", box(200, 120, 480, 280))
        cap = anchor("caption", "figcaption", "Figure 2: training and validation loss per epoch", box(200, 410, 480, 30))
        case(f"ambiguous_figure_{i}", "ambiguous", "circle around a figure and its caption", "what does this show?",
             [circle_stroke(box(200, 120, 480, 320), rng.randint(5, 15))], [img, cap], ["img", "caption"], ambiguous=True)


def ocr_cases():
    labels = [("title", "Revenue by quarter", box(420, 110, 300, 30)), ("legend0", "2025", box(900, 160, 60, 20)),
              ("legend1", "2026", box(900, 190, 60, 20)), ("xlabel", "Quarter", box(560, 640, 100, 22)),
              ("ylabel", "USD (millions)", box(150, 360, 130, 22)), ("peak", "2.1", box(760, 230, 40, 20)),
              ("note", "Source: internal finance report", box(400, 675, 320, 18)), ("q3", "Q3", box(640, 610, 30, 20))]
    for i, (key, text, b) in enumerate(labels):
        chart = anchor("chart", "canvas", "", box(140, 100, 900, 580))
        ocr = [anchor(f"ocr-{j}", "ocr", t, bb) for j, (_, t, bb) in enumerate(labels)]
        case(f"ocr_chart_{key}", "ocr", "canvas chart: only OCR blocks carry text; box around one label",
             "what does this mean?", [rect_around(b, rng.randint(3, 10))], [chart, *ocr], [f"ocr-{i}"])


if __name__ == "__main__":
    for old in OUT.glob("*.json"):
        old.unlink()
    web_cases(); pdf_cases(); ambiguous_cases(); ocr_cases()
    print(len(list(OUT.glob("*.json"))), "cases")
```

Run (from `server/`): `python tests/eval_cases/generate.py` → `43 cases`.

- [ ] **Step 2: Write the failing tests**

`server/tests/test_evaluation.py`:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import evaluation  # noqa: E402

TESTS = Path(__file__).parent
DIRS = [TESTS / "cases", TESTS / "eval_cases"]


def test_cases_load_and_normalize():
    cases = evaluation.load_cases(DIRS)
    assert len(cases) >= 50
    cats = {c["category"] for c in cases}
    assert {"web", "pdf", "ambiguous", "ocr", "golden"} <= cats
    assert all(c["intended"] for c in cases)


def test_run_case_scores_top1_and_top3():
    case = {"name": "t", "category": "web", "question": "q", "surface": "web", "canvas": {"width": 1280, "height": 720},
            "marks": [{"type": "rectangle", "role": "reference", "x": 100, "y": 100, "width": 200, "height": 60}],
            "anchors": [{"id": "hit", "type": "p", "text": "hit", "bbox": {"x": 100, "y": 100, "width": 200, "height": 60}},
                        {"id": "near", "type": "p", "text": "near", "bbox": {"x": 100, "y": 150, "width": 200, "height": 60}}],
            "intended": ["near"], "ambiguous": False}
    result = evaluation.run_case(case)
    assert result["predicted"] == ["hit"] and result["top1"] is False and result["top3"] is True


def test_summary_metrics_shape():
    summary = evaluation.summarize([evaluation.run_case(c) for c in evaluation.load_cases(DIRS)])
    assert {"cases", "top1", "top3", "abstain_rate", "p50_ms", "p95_ms", "by_category"} <= set(summary)
    assert 0.0 <= summary["top1"] <= summary["top3"] <= 1.0


def test_no_regression_against_committed_baseline():
    baseline = json.loads((TESTS / "eval_baseline.json").read_text(encoding="utf-8"))
    summary = evaluation.summarize([evaluation.run_case(c) for c in evaluation.load_cases(DIRS)])
    assert summary["top1"] >= baseline["top1"] - 0.02


def test_trace_replay(tmp_path):
    record = {"question": "What is this?", "privacy_policy": "crop_only",
              "surface": {"kind": "web", "url": "", "title": "", "viewport": {"width": 1280, "height": 720}},
              "marks": [{"kind": "rectangle", "role": "reference", "bbox": {"x": 100, "y": 100, "width": 200, "height": 60}}],
              "candidates": [{"candidate_id": "hit", "source": "dom", "text": "hit", "provenance": {"extractor": "t"},
                              "bbox": {"x": 100, "y": 100, "width": 200, "height": 60}}],
              "resolution": {"selected_candidate_id": "hit"}}
    (tmp_path / "2026-09-23.jsonl").write_text(json.dumps(record) + "\n{not json\n", encoding="utf-8")
    records = evaluation.load_traces(tmp_path)
    assert len(records) == 1
    assert evaluation.run_trace(records[0])["top1"] is True
```

Also extend parity in `server/tests/test_resolver_cases.py`: after `CASES = …` add

```python
EVAL_CASES = sorted((Path(__file__).parent / "eval_cases").glob("*.json"))
```

and change the `test_js_matches_python` parametrization to `CASES + EVAL_CASES` (ids `[p.stem for p in CASES + EVAL_CASES]`).

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_evaluation.py -v` → FAIL (`cannot import name 'evaluation'`).

- [ ] **Step 4: Implement `server/app/evaluation.py`**

```python
"""Resolver evaluation over labelled cases and recorded traces. Metrics: top-1 / top-3 accuracy against the
intended candidate(s), abstain rate (confidence < 0.6), resolver latency. Uses the same contract adapter as the
server so the numbers describe what /api/ask actually does."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from app.contracts import SpatialContext, from_v2, resolver_inputs
from app.resolver import resolve_marks


def _normalize(raw: dict, name: str) -> dict:
    if "intended" in raw:
        intended, category = raw["intended"], raw.get("category", "uncategorized")
    else:  # golden regression case: expectation doubles as the intended target
        expect = raw["expect"]
        intended, category = (expect["tops"] if "tops" in expect else [expect["top"]]), "golden"
    return {"name": name, "category": category, "question": raw.get("question", "what is this?"),
            "surface": raw.get("surface", "web"), "canvas": raw["canvas"], "marks": raw["marks"],
            "anchors": raw["anchors"], "intended": intended, "ambiguous": bool(raw.get("ambiguous")),
            "multi": "expect" in raw and "tops" in raw["expect"]}


def load_cases(dirs: list[Path]) -> list[dict]:
    cases = []
    for directory in dirs:
        for path in sorted(Path(directory).glob("*.json")):
            cases.append(_normalize(json.loads(path.read_text(encoding="utf-8")), path.stem))
    return cases


def _score(ctx: SpatialContext, intended: list, multi: bool) -> dict:
    started = perf_counter()
    resolution = resolve_marks(*resolver_inputs(ctx))
    latency = (perf_counter() - started) * 1000
    per_mark = [[item["id"] for item in c.get("anchors_ranked", [])] for c in resolution["candidates"]]
    if multi:
        tops = [ranked[0] if ranked else None for ranked in per_mark]
        top1 = top3 = tops == intended
        predicted = tops
    else:
        ranked = per_mark[0] if per_mark else []
        top1 = bool(ranked) and ranked[0] in intended
        top3 = any(item in intended for item in ranked[:3])
        predicted = ranked[:1]
    return {"top1": top1, "top3": top3, "abstained": resolution["confidence"] < 0.6,
            "latency_ms": latency, "predicted": predicted, "confidence": resolution["confidence"]}


def run_case(case: dict) -> dict:
    ctx = from_v2(question=case["question"], marks=case["marks"], anchors=case["anchors"], canvas=case["canvas"],
                  page={"surface": case["surface"]}, privacy_policy="anchors_only")
    return {"name": case["name"], "category": case["category"], **_score(ctx, case["intended"], case.get("multi", False))}


def load_traces(directory: Path) -> list[dict]:
    records = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


def run_trace(record: dict) -> dict:
    """Replay a trace. Expected = a hand-added `label` (candidate id) if present, else what was resolved then."""
    ctx = SpatialContext.model_validate({k: record[k] for k in ("surface", "marks", "candidates", "question", "privacy_policy")})
    expected = record.get("label") or (record.get("resolution") or {}).get("selected_candidate_id")
    return {"name": record.get("request_id", "trace"), "category": "trace", **_score(ctx, [expected], False)}


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))] if ordered else 0.0


def summarize(results: list[dict]) -> dict[str, Any]:
    def block(items: list[dict]) -> dict[str, Any]:
        n = len(items) or 1
        return {"cases": len(items), "top1": round(sum(r["top1"] for r in items) / n, 4),
                "top3": round(sum(r["top3"] for r in items) / n, 4),
                "abstain_rate": round(sum(r["abstained"] for r in items) / n, 4)}
    latencies = [r["latency_ms"] for r in results]
    categories = sorted({r["category"] for r in results})
    return {**block(results), "p50_ms": round(median(latencies), 3) if latencies else 0.0,
            "p95_ms": round(_percentile(latencies, 0.95), 3),
            "by_category": {c: block([r for r in results if r["category"] == c]) for c in categories},
            "failures": [r["name"] for r in results if not r["top1"]]}
```

- [ ] **Step 5: Create `scripts/eval.py`**

```python
"""Resolver eval CLI.
  python scripts/eval.py cases [--json] [--baseline server/tests/eval_baseline.json] [--write-baseline PATH]
  python scripts/eval.py traces <log dir> [--json]
Exits 1 when --baseline is given and top-1 dropped by more than 2 points."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from app import evaluation  # noqa: E402

TESTS = ROOT / "server" / "tests"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["cases", "traces"])
    parser.add_argument("directory", nargs="?")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument("--write-baseline")
    args = parser.parse_args()
    if args.mode == "cases":
        results = [evaluation.run_case(c) for c in evaluation.load_cases([TESTS / "cases", TESTS / "eval_cases"])]
    else:
        if not args.directory:
            parser.error("traces mode needs a log directory")
        results = [evaluation.run_trace(r) for r in evaluation.load_traces(Path(args.directory))]
    summary = evaluation.summarize(results)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"cases {summary['cases']}  top1 {summary['top1']:.1%}  top3 {summary['top3']:.1%}  "
              f"abstain {summary['abstain_rate']:.1%}  p50 {summary['p50_ms']} ms  p95 {summary['p95_ms']} ms")
        for name, block in summary["by_category"].items():
            print(f"  {name:<11} n={block['cases']:<3} top1 {block['top1']:.1%}  top3 {block['top3']:.1%}")
        if summary["failures"]:
            print("  top-1 misses:", ", ".join(summary["failures"]))
    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps({k: summary[k] for k in ("cases", "top1", "top3", "abstain_rate", "by_category")},
                                                        indent=2) + "\n", encoding="utf-8")
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        if summary["top1"] < baseline["top1"] - 0.02:
            print(f"REGRESSION: top1 {summary['top1']:.1%} < baseline {baseline['top1']:.1%} - 2pt")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Generate baseline, run everything**

Run (repo root): `python scripts/eval.py cases --write-baseline server/tests/eval_baseline.json`
Expected: prints `cases 50  top1 …` with per-category lines. Record the printed numbers in `docs/MEMORY.md` (Facts learned) — do not edit the cases to raise the score; misses (e.g. point-on-button, ambiguous) are the signal sub-project 2 must improve.
Run (from `server/`): `python -m pytest -q` → all pass (parity now also covers 43 eval cases).

- [ ] **Step 7: Commit**

```bash
git add server/app/evaluation.py scripts/eval.py server/tests/eval_cases server/tests/eval_baseline.json server/tests/test_evaluation.py server/tests/test_resolver_cases.py
git commit -m "feat: resolver eval harness, 43 labelled cases, committed baseline"
```

---

### Task 8: Documentation and task board

**Files:**
- Modify: `README.md`, `docs/ARCHITECTURE.md`, `docs/AGENTS.md`, `docs/TASKS.md`, `docs/MEMORY.md`, `docs/superpowers/specs/2026-09-23-spatial-core-foundation-design.md`

- [ ] **Step 1: README sections**

Append to `README.md`:

```markdown
## Tracing (opt-in)

Toggle **Keep a local trace log** in the extension popup, or set `SPATIAL_TRACE=on` in `server/.env`. Each ask
appends one JSON line (question, answer, marks, candidates, what was resolved, timings — never images) to
`%APPDATA%\Spatial\logs\YYYY-MM-DD.jsonl` (override with `SPATIAL_LOG_DIR`). Kept 14 days / 50 MB.
`GET /api/traces/export` downloads everything; `DELETE /api/traces` wipes it.

## Eval

```bash
python scripts/eval.py cases                     # top-1/top-3 over golden + eval cases
python scripts/eval.py traces "%APPDATA%\Spatial\logs"   # replay your own traces
python scripts/export_schema.py                  # regenerate schema/spatial-context.v3.json
```
```

- [ ] **Step 2: Architecture, agents, spec**

`docs/ARCHITECTURE.md` §1: replace "Validate protocol (v2)…" step with "Convert the request to a `SpatialContext` (v3 as-is; v2 via `contracts.from_v2`); OCR blocks become candidates when a crop with geometry is attached"; add a line "**Contract** — `server/app/contracts.py`, schema `schema/spatial-context.v3.json`". Add "**Trace log** — `server/app/trace.py`" and "**Eval** — `server/app/evaluation.py`, `scripts/eval.py`".
`docs/AGENTS.md` Commands: add `python scripts/eval.py cases` and update the pytest count to the number printed in Task 7 Step 6.
Spec: set **Status** to `Implemented (2026-09-23)`, and record the plan's deviations under a new "Implementation notes" heading: BBox x/y may be negative; OCR dedupe = ≥80% inside + text containment; eval cases live in `server/tests/eval_cases/` with `intended` labels (golden cases normalized on load); retention runs after each write (no startup pass).

- [ ] **Step 3: TASKS and MEMORY**

`docs/TASKS.md`: mark sub-project 1 items `[x]`, roadmap row 1 → "Done", "Now" → next item "Sub-project 2 experiments E1–E4". `docs/MEMORY.md`: add the baseline numbers, "diagram note now only when OCR also found no text", "first live Jev call: 200 OK, ~1.2 s, 401 input tokens; thin criteria gave `none` — criteria must describe each candidate".

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest -q` (server) and `node --test extension/tests/geometry.test.mjs` → pass.

```bash
git add README.md docs
git commit -m "docs: tracing, eval, contract; sub-project 1 done"
```
