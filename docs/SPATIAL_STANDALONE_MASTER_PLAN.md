# SPATIAL — Standalone Product & Orbyn-Ready Architecture Plan

**Date:** 18 September 2026  
**Status:** Proposed canonical standalone plan  
**Product:** Spatial — Point & Ask  
**Primary goal:** Make Spatial the most reliable local-first system for turning a human spatial reference (“this”, “that chart”, “this field”, “this paragraph”) into a grounded, inspectable, semantically resolved software object that downstream models can reason over.  
**Secondary goal:** Keep Spatial useful as a standalone browser/PDF product while making its contracts clean enough to later become Orbyn’s `Spatial Context` primitive without a rewrite.

---

# 0. Executive Summary

Spatial is already a strong prototype:

- Chrome MV3 extension;
- pen/circle/box drawing;
- DOM anchor collection;
- PDF text-layer integration;
- deterministic geometry ranking;
- crop capture;
- OCR fallback;
- local/cloud answer providers;
- research mode;
- voice input/output;
- SQLite context/history;
- visible highlight of what the system resolved.

The central architecture is already correct:

> **Human marks a region → Spatial discovers real candidate objects → deterministic geometry narrows candidates → semantic resolution decides what the human meant → answer model reasons about that resolved object.**

The main architectural upgrade is to make **semantic resolution explicit** rather than leaving it buried inside the answer LLM prompt.

Jev should become the first **System-One semantic decision provider**:

> **Geometry answers “where?”  
> Jev answers “which object?”  
> The answer model answers “what does it mean?”**

This must be paired with improvements that are at least as important as Jev:

1. stable candidate/object identity;
2. better DOM/PDF/SVG/canvas candidate extraction;
3. confidence calibration instead of hand-tuned confidence;
4. explicit ambiguity/abstention behavior;
5. candidate provenance;
6. viewport + document coordinate normalization;
7. iframe/shadow-DOM support;
8. robust PDF object grouping;
9. structured crop/object context;
10. privacy and provider-policy controls;
11. resolver evals with ground truth;
12. performance budgets;
13. observability/replay;
14. offline-first fallbacks;
15. a versioned `SpatialContext` contract that can later plug into Orbyn.

The standalone product should remain **read-only / reference-first**.

It may:
- identify;
- explain;
- compare;
- highlight;
- ask clarifying questions;
- research;
- speak;
- export a resolved context object.

It should **not become an autonomous clicking agent** by itself.

That preserves its simplicity and makes later Orbyn integration clean:

```text
Spatial
  = reference + grounding + semantic resolution

Orbyn
  = authority + permissions + execution + verification
```

---

# 1. Current State — Preserve What Is Already Good

The current product already contains the following useful architecture and should not be rewritten blindly.

## 1.1 Browser Extension

Current components:

```text
content.js
  - pen / circle / box overlay
  - anchor collection
  - ask panel
  - mic / TTS controls
  - PDF textLayer integration
  - highlight resolved anchors

background.js
  - hotkey
  - captureVisibleTab
  - crop pipeline
  - offscreen recording
  - server requests
  - provider/privacy policy

geometry.js
  - strokeToMark
  - shapeToMark
  - bbox normalization
  - simplification
  - candidate filtering
  - anchor ranking
```

Keep this split, but formalize contracts between these modules.

---

## 1.2 FastAPI Server

Current components:

```text
resolver.py
  - normalize marks
  - IoU / overlap ranking
  - confidence
  - deterministic resolution

providers.py
  - prompt building
  - Ollama
  - NVIDIA
  - OpenAI
  - other answer providers

ocr.py
  - RapidOCR / ONNX fallback

audio.py
  - STT
  - TTS

research.py
  - external search
  - grounded research

store.py
  - SQLite
  - context
  - marks
  - resolution
  - Q/A history
```

Preserve this basic service separation, but split semantic resolution out of `providers.py`.

---

## 1.3 Existing Correct Product Principles

Keep these as hard invariants:

### A. Mark is reference, never authority

Spatial should never interpret a circle as permission to click/delete/submit.

### B. Deterministic geometry first

Cheap deterministic narrowing before model calls.

### C. Privacy tiers

At minimum:
- `anchors_only`
- `crop_only`
- `full_frame`

Expand these later rather than removing them.

### D. Fallbacks

A provider outage must not make the app unusable.

### E. Visible grounding

Always show the user what Spatial believes they referred to.

### F. Local-first

The best standalone identity is:
> **Point at anything. Ask naturally. Keep control of your screen data.**

---

# 2. New Canonical Architecture

The new architecture should become:

```text
┌──────────────────────────────────────────────────────────────────┐
│                         HUMAN INPUT                              │
│  mark • pointer • box • freehand • question • voice • hotkey    │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SPATIAL MARK NORMALIZER                       │
│  viewport coords • document coords • mark polygon • bbox • role  │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     CANDIDATE DISCOVERY                          │
│ DOM • PDF • SVG • canvas hints • OCR • accessibility • vision   │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   DETERMINISTIC PREFILTER                        │
│ geometry • visibility • role • containment • overlap • context  │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                  SEMANTIC TARGET RESOLVER                        │
│      Jev Choice / Noul / Score + local fallback                  │
│      → target distribution + confidence + abstention             │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    CONTEXT ASSEMBLER                             │
│ resolved object • alternatives • OCR • crop • page metadata     │
│ nearby objects • user history • privacy-filtered context         │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     ANSWER / RESEARCH LAYER                      │
│ local model • cloud model • grounded research • tutor modes      │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   RESPONSE + EXPLAINABILITY                      │
│ answer • highlight • confidence • alternatives • citations      │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    CONTEXT / REPLAY STORE                        │
│ context id • mark • candidates • resolution • answer • evidence │
└──────────────────────────────────────────────────────────────────┘
```

---

# 3. Core Data Model

Before adding more intelligence, define stable schemas.

## 3.1 `SpatialMark`

```typescript
type SpatialMark = {
  markId: string;
  kind: "freehand" | "circle" | "box" | "point" | "arrow";
  role?: "reference" | "source" | "target" | "compare_a" | "compare_b";
  viewportPoints: Array<{x: number; y: number}>;
  documentPoints?: Array<{x: number; y: number}>;
  viewportBBox: BBox;
  documentBBox?: BBox;
  pageIndex?: number;
  createdAt: number;
};
```

---

## 3.2 `CandidateObject`

```typescript
type CandidateObject = {
  candidateId: string;
  source:
    | "dom"
    | "pdf_text"
    | "svg"
    | "canvas"
    | "ocr"
    | "accessibility"
    | "vision";

  objectType?: string;
  role?: string;
  tagName?: string;

  label?: string;
  text?: string;
  semanticDescription?: string;

  viewportBBox?: BBox;
  documentBBox?: BBox;

  parentChain?: string[];
  nearbyText?: string[];
  attributes?: Record<string, string>;

  geometry: {
    iou: number;
    overlapMark: number;
    overlapCandidate: number;
    centerDistance: number;
    containment: "inside" | "contains" | "overlap" | "near" | "none";
  };

  state?: {
    visible?: boolean;
    enabled?: boolean;
    selected?: boolean;
    focused?: boolean;
  };

  provenance: {
    extractor: string;
    extractorVersion: string;
    observationId: string;
  };
};
```

---

## 3.3 `SemanticResolution`

```typescript
type SemanticResolution = {
  selectedCandidateId?: string;
  alternatives: Array<{
    candidateId: string;
    probability: number;
  }>;
  semanticConfidence: number;
  geometricConfidence: number;
  fusedConfidence: number;
  abstained: boolean;
  ambiguityReason?: string;
  provider: string;
  modelVersion?: string;
};
```

---

## 3.4 `SpatialContext`

This becomes the long-term export contract.

```typescript
type SpatialContext = {
  contextId: string;
  page: {
    url: string;
    title?: string;
    documentType: "web" | "pdf" | "unknown";
    viewport: {width: number; height: number};
    scrollX: number;
    scrollY: number;
  };

  marks: SpatialMark[];

  candidates: CandidateObject[];

  resolution?: SemanticResolution;

  crop?: {
    imageRef?: string;
    width: number;
    height: number;
    paddingPx: number;
  };

  ocr?: {
    text: string;
    blocks?: Array<{
      text: string;
      bbox: BBox;
      confidence?: number;
    }>;
  };

  question?: string;
  privacyTier: "anchors_only" | "crop_only" | "full_frame";
  createdAt: number;
};
```

This contract is intentionally useful both standalone and later inside Orbyn.

---

# 4. Jev Integration — System-One Semantic Resolver

Jev should not replace geometry.

Jev should not replace OCR.

Jev should not replace the answer LLM.

Jev should become a specialized semantic resolver between deterministic candidate extraction and answer synthesis.

## 4.1 System-One / System-Two Split

```text
SYSTEM ONE
Jev
- target selection
- candidate ranking
- ambiguity probability
- object classification
- relation scoring
- source selection

SYSTEM TWO
LLM/VLM
- explanation
- tutoring
- reasoning
- comparison
- synthesis
- research
- follow-up questions
```

---

## 4.2 Jev Interface

Create:

```text
server/app/system_one/
  provider.py
  types.py
  resolver.py
  calibration.py
  providers/
    jev.py
    deterministic.py
    local_fallback.py
```

Generic interface:

```python
class SystemOneProvider:
    async def choose(self, state, question, options): ...
    async def noul(self, state, question): ...
    async def score(self, state, question, scale): ...
```

Jev stays behind this interface.

Do not spread Jev-specific calls throughout the application.

---

## 4.3 First Jev Use Case

Input:

```text
question:
"explain this chart"

mark:
circle around chart region

candidates:
Chart_1
Legend_1
TextBox_3
Shape_7
```

Jev:

```text
Chart_1     0.94
Legend_1    0.03
TextBox_3   0.02
Shape_7     0.01
```

The answer model receives:

```text
Resolved object:
Chart_1

Other plausible candidates:
Legend_1 (0.03)
...
```

not an unstructured dump of every nearby anchor.

---

# 5. Confidence Architecture

The current geometric confidence should evolve into explicit multi-signal confidence.

## 5.1 Signals

```text
geometry confidence
semantic confidence
extractor trust
text quality
object stability
mark specificity
candidate margin
OCR quality
```

---

## 5.2 Fused Confidence

Do not immediately invent a magical formula.

Start with a transparent configurable combiner.

Example:

```python
fused = combine(
    geometry=...,
    semantic=...,
    extractor_trust=...,
    margin=...
)
```

Then calibrate on real labelled data.

---

## 5.3 UX Bands

Do not expose fake precision to users.

Use human-readable states:

### Confident
> “You marked the revenue chart.”

### Ambiguous
> “I think you mean the chart, but the legend is also inside your mark.”

Show:
- Use chart
- Use legend
- Circle tighter

### Unresolved
> “I’m not confident what you meant. Circle a smaller region.”

---

# 6. Candidate Discovery V2

This is as important as Jev.

If the correct object never enters the candidate set, Jev cannot recover it.

## 6.1 DOM Extraction

Improve current anchor extraction to capture:

- semantic tags;
- ARIA role;
- aria-label;
- title;
- alt;
- input label;
- associated `<label>`;
- button text;
- link text;
- table headers;
- figure/figcaption;
- list hierarchy;
- data-* attributes where safe;
- nearest heading;
- parent section.

---

## 6.2 Shadow DOM

Support open Shadow DOM traversal.

Maintain:
- host chain;
- local bbox;
- semantic ancestry.

Closed Shadow DOM should gracefully fall back to accessibility/vision.

---

## 6.3 Iframes

Support:
- same-origin iframe DOM traversal;
- frame-local → top-level coordinate transforms;
- frame provenance.

Cross-origin iframe:
- geometry + screenshot candidate;
- accessibility if available;
- never pretend DOM grounding exists if it does not.

---

## 6.4 SVG

SVG deserves first-class support.

Extract:
- `<svg>`;
- `<g>`;
- `<text>`;
- `<rect>`;
- `<circle>`;
- `<path>`;
- accessible labels;
- nearby legend text.

Group primitive SVG elements into meaningful semantic objects when possible.

Example:

```text
12 bar rectangles
+ axis labels
+ title
```

should produce:

```text
BarChart_1
```

not only 25 low-level shapes.

---

## 6.5 Canvas

Canvas is hard because DOM object identity is absent.

Strategy:

### Tier 1
Use surrounding DOM:
- aria-label;
- canvas label;
- nearby text;
- caption;
- page section.

### Tier 2
OCR crop.

### Tier 3
vision candidate segmentation.

Canvas-derived objects must carry lower grounding trust.

---

# 7. PDF Resolution V2

PDF support can become one of Spatial’s strongest standalone use cases.

## 7.1 Text Layer Grouping

Do not expose each span independently.

Group into:
- word;
- line;
- paragraph;
- heading;
- equation region;
- table cell;
- figure caption.

---

## 7.2 Figure Detection

Infer figures from:
- text-free regions;
- captions;
- images;
- bounding clusters.

Candidate:

```text
Figure 3 — Transformer architecture
```

is much better than:
```text
image bbox 872x410
```

---

## 7.3 Equation Detection

Detect:
- math-heavy text;
- MathJax/KaTeX on web;
- PDF equation blocks;
- equation numbering.

Expose:

```text
Equation_7
```

with nearby explanatory paragraph.

---

## 7.4 Tables

Build candidate hierarchy:

```text
Table_2
  Header
  Row_1
  Row_2
  Cell_2_3
```

User can circle:
- entire table;
- row;
- cell;
- header.

---

# 8. Multi-Mark Semantics

Expand beyond one mark.

## 8.1 Compare

```text
Mark A
Mark B

"What's the difference between these?"
```

---

## 8.2 Source / Target

```text
SOURCE
TARGET

"How does this lead to this?"
```

Standalone Spatial only explains the relationship.

Later Orbyn may interpret the same structure as an action proposal.

---

## 8.3 Sequence

Allow 1, 2, 3 numbering:

```text
1 → 2 → 3
```

Question:
> “Explain the flow through these.”

---

## 8.4 Exclude

Potential future interaction:

```text
circle object
scribble X over legend
```

Meaning:
> explain chart excluding legend.

Do not add until the simple multi-mark model is stable.

---

# 9. Bidirectional Spatial Language

Standalone Spatial should also point back to the user.

## AI → Human Highlight

Answer:
> “The increase happens at this bar.”

Pulse or outline the exact object.

## Multi-highlight

When an answer references multiple objects:
- highlight A;
- then B;
- optionally animate relationship.

## Explain grounding

Optional small tooltip:

```text
Resolved:
Quarterly Revenue chart

Confidence:
High

Why:
Inside mark + semantic match "chart"
```

Keep this optional, not noisy.

---

# 10. Answer Engine V2

Separate **resolution** from **answering** cleanly.

Current:
```text
anchors → prompt → LLM implicitly resolves + answers
```

New:
```text
anchors → resolver → resolved context → answerer
```

---

## 10.1 Prompt Contract

Answer provider receives:

```text
QUESTION
...

RESOLVED OBJECT
type:
text:
semantic description:

SPATIAL CONTEXT
mark relation:
nearby objects:

OCR
...

HISTORY
...

INSTRUCTIONS
answer only about resolved target
```

---

## 10.2 Answer Modes

Make modes explicit:

### Explain
“What is this?”

### Tutor
“Help me understand this without just giving the answer.”

### Summarize
“Summarize this section.”

### Compare
“How is A different from B?”

### Research
“Find current research about this.”

### Define
“What does this term mean?”

### Trace
“How does this connect to the previous section?”

This makes standalone Spatial more useful than a generic screenshot-QA tool.

---

# 11. Research Mode V2

Current research mode is a useful differentiator.

Improve it into a pipeline:

```text
resolved target
↓
query planner
↓
search
↓
source ranking
↓
source fetch
↓
grounded synthesis
↓
citations
```

Important:
- research should use the resolved object, not only the user's vague phrase;
- clearly distinguish page-local answer from web-grounded research;
- show source freshness;
- allow “research this” as a second-step button.

---

# 12. Voice

Voice is already present and should be improved, not overbuilt.

## Goals

User draws and says:
> “Explain this graph.”

No keyboard.

## Improvements

- push-to-talk first;
- optional continuous follow-up later;
- VAD;
- cancel;
- playback interruption;
- choose concise/detailed voice answers;
- do not send audio if local transcription is enabled.

---

# 13. Local-First Provider Policy

Make provider routing explicit.

## Privacy tiers

### `local_only`
- local OCR;
- local resolver fallback;
- local LLM;
- no screenshot/network.

### `anchors_only`
Cloud receives:
- question;
- structured candidates;
- selected text;
- no crop.

### `crop_only`
Cloud receives:
- marked crop;
- minimal anchor context.

### `full_frame`
Explicit opt-in only.

---

## Provider Classes

Separate:

```text
semantic resolver
answer provider
vision provider
research provider
speech provider
```

Do not create one giant provider chain for everything.

---

# 14. Jev Privacy Policy

Jev should ideally receive:

- question/reference phrase;
- small candidate list;
- role;
- label;
- candidate descriptions;
- geometry relation;
- minimal page context.

Avoid sending:
- full screenshot;
- entire document;
- full page DOM;
- passwords;
- tokens;
- private hidden text;
- unrelated page content.

Use ephemeral candidate aliases.

Example:

```text
A
B
C
D
```

rather than exposing internal DOM path if unnecessary.

---

# 15. OCR V2

Current RapidOCR fallback is useful.

Improve:

- return blocks, not only text;
- preserve bbox;
- preserve confidence;
- line grouping;
- orientation detection;
- crop preprocessing;
- high-DPI handling;
- PDF-aware mode;
- equation flag;
- table-like layout flag.

OCR output should become candidates, not just prompt text.

---

# 16. Vision Fallback

Vision should create candidate objects.

Bad:

```text
VLM directly answers everything
```

Better:

```text
crop
↓
vision candidate detector
↓
CandidateObject[]
↓
semantic resolver
↓
answer model
```

Even when no “real” DOM object exists, keep the same architecture.

---

# 17. Coordinate System Hardening

Spatial systems fail on coordinate mismatch.

Explicitly model:

- CSS pixels;
- device pixels;
- viewport coordinates;
- document coordinates;
- iframe local coordinates;
- PDF page coordinates;
- crop coordinates;
- zoom;
- `devicePixelRatio`;
- browser zoom;
- page scale;
- PDF viewer scale;
- scroll offsets.

Create one canonical geometry library and golden tests.

Do not duplicate geometry logic independently in client and server unless parity tests are mandatory.

---

# 18. Geometry V2

Current IoU is not enough.

Add:
- overlap(mark, candidate);
- overlap(candidate, mark);
- center-in-polygon;
- candidate center distance;
- polygon intersection;
- freehand density;
- boundary distance;
- containment class.

Example:
A large container containing the mark may have high overlap but should lose to a smaller exact child.

Use ranking features, not one scalar.

---

# 19. Parent/Child Candidate Graph

Represent structural relationships:

```text
Section
  Figure
    Chart
      Legend
      Axis
      Series
```

This allows semantic resolution to understand:
- “this chart” → Chart;
- “this legend” → Legend;
- “this section” → Section.

Jev becomes more effective with hierarchy.

---

# 20. Resolver Explainability

Do not expose hidden chain-of-thought.

Expose structured evidence:

```text
Selected:
Chart_1

Signals:
- 84% inside mark
- type = chart
- user phrase contains “chart”
- nearest heading = Revenue
- alternative Legend_1 had lower semantic fit
```

This is enough for debugging and trust.

---

# 21. Clarification UX

Ambiguity should become a product strength.

If two candidates are close:

```text
Did you mean:

[A] Revenue chart
[B] Legend
```

Render both with numbered overlays.

User clicks one.

That user correction becomes eval/training data.

---

# 22. Correction Loop

Store:

```text
initial candidates
initial pick
confidence
user correction
final pick
```

This becomes the most valuable standalone quality dataset.

Use it for:
- evaluation;
- confidence calibration;
- prompt/provider comparison;
- future fine-tuning if appropriate.

Do not automatically train/upload without consent.

---

# 23. Context History

Current Q/A history should become target-aware.

History item:

```text
question
resolved object
page/document
answer
timestamp
```

Follow-up:
> “Why?”

should inherit the prior resolved object unless:
- user makes a new mark;
- page changes materially;
- context becomes stale.

---

# 24. Staleness

Web pages change.

Store an `observationId`.

If:
- navigation;
- DOM mutation;
- viewport change;
- PDF page change;
- substantial layout shift;

then prior candidate handles may be stale.

Re-resolve before highlighting.

Standalone Spatial should never highlight an old bbox without checking that it still corresponds to the current page.

---

# 25. Mutation Observer Strategy

Use a lightweight MutationObserver.

Do not continuously rescan the entire page.

Track:
- candidate-relevant subtree changes;
- navigation;
- iframe changes;
- content replacements.

Debounce.

---

# 26. Performance Budgets

Set measurable budgets.

Proposed initial targets (to validate, not blindly hard-code):

### Draw feedback
< 16ms/frame perceived drawing.

### Local candidate collection
target < 100ms typical page.

### Deterministic resolution
target < 20ms typical candidate set.

### Jev semantic resolution
measure p50/p95/p99.

### Crop capture
target < 250ms.

### First streamed answer token
local/cloud separately measured.

### Full interaction
Measure:
```text
mark end → highlight
mark end → semantic resolution
ask → first answer token
```

Do not optimize only model latency.

---

# 27. Cancellation

Every expensive operation should accept cancellation:

- crop;
- OCR;
- Jev;
- answer model;
- research;
- STT/TTS.

New mark/question should cancel obsolete in-flight work.

---

# 28. Request Identity

Add:

```text
requestId
contextId
observationId
markId
```

Every async result must match the active request before UI update.

This prevents stale answers/highlights.

---

# 29. SSE Hardening

For SSE:
- explicit event types;
- sequence numbers;
- heartbeat;
- disconnect handling;
- cancellation;
- final/error events;
- retry policy;
- request id in every event.

Example:

```text
resolution.started
resolution.completed
answer.token
answer.completed
research.started
research.source
error
```

---

# 30. Server API Versioning

Add `/v1/`.

Suggested endpoints:

```text
POST /v1/context/resolve
POST /v1/answer/stream
POST /v1/research/stream
POST /v1/audio/transcribe
POST /v1/audio/speak
GET  /v1/health
GET  /v1/providers
```

Later:
```text
POST /v1/eval/replay
```

---

# 31. Store Schema V2

Tables:

```text
contexts
marks
candidates
resolutions
questions
answers
provider_calls
corrections
research_sources
eval_labels
```

Keep raw images optional and short-lived.

Default:
- do not persist screenshot crop unless user opts in;
- persist hash/metadata where enough.

---

# 32. Replayability

A good resolver needs reproducible cases.

Create a debug bundle:

```text
context.json
candidates.json
mark.json
question.txt
optional crop
ground_truth.json
```

Replay without loading live website where possible.

This becomes your eval corpus.

---

# 33. Golden Test Corpus

Create manually curated cases:

## Web
- simple button;
- chart;
- card;
- nested text;
- form field;
- table;
- sidebar;
- icon-only control.

## PDF
- paragraph;
- equation;
- figure;
- table;
- caption;
- multi-column;
- scanned page.

## Difficult
- overlapping elements;
- huge container;
- sticky header;
- transformed element;
- iframe;
- shadow DOM;
- canvas;
- zoomed page.

---

# 34. Jev Evaluation

Compare:

1. geometry only;
2. geometry + heuristics;
3. geometry + answer LLM implicit resolution;
4. geometry + Jev;
5. geometry + local structured model;
6. geometry + Jev + spatial semantics.

Metrics:

- top-1 target accuracy;
- top-3;
- confidence calibration;
- abstention quality;
- false-high-confidence rate;
- latency;
- cost;
- candidate-count sensitivity;
- correction rate.

Most important:

> **When the resolver is wrong, does it know enough to avoid pretending certainty?**

---

# 35. Answer Quality Eval

Target resolution can be correct while answer is bad.

Separate metrics:

### Grounding
Did it answer about the right object?

### Correctness
Was the explanation correct?

### Relevance
Did it answer the question?

### Scope
Did it avoid unrelated page content?

### Citation quality
Research mode.

### Concision
Default Point & Ask should be fast.

---

# 36. Privacy Tests

Automated checks:

- hidden DOM content not sent unexpectedly;
- password fields excluded;
- inputs marked sensitive excluded;
- cookies never sent;
- local-only mode makes zero network calls;
- anchors-only sends no image;
- crop-only sends only crop;
- logs redact secrets;
- provider request preview matches policy.

---

# 37. Security

Browser extension permissions should be minimal.

Audit:
- host permissions;
- captureVisibleTab;
- offscreen;
- storage;
- microphone;
- network access.

Prefer optional host permissions where possible.

Never inject into sensitive restricted Chrome pages where unsupported.

---

# 38. Sensitive Field Detection

Before candidate/prompt export, detect:
- password;
- OTP;
- credit card;
- auth token;
- secret keys;
- SSN-like patterns;
- private input fields.

Policy:
- redact;
- local-only;
- warn;
- block provider send.

---

# 39. Provider Gateway

Create a single outbound provider gateway.

Responsibilities:
- privacy tier enforcement;
- redaction;
- timeout;
- retry;
- rate limit;
- API keys;
- cost accounting;
- provider availability;
- cancellation;
- request audit metadata.

All Jev/LLM/research external calls route through it.

---

# 40. API Keys

Store server-side or OS-secure.

Do not expose provider credentials inside extension content scripts.

---

# 41. Standalone Product UX

Keep the product emotionally simple.

Primary flow:

```text
1. Hold hotkey
2. Circle
3. Ask
4. See what Spatial understood
5. Get answer
```

The architecture can be complex; the interaction should not be.

---

# 42. Ask Panel V2

Show:

```text
[resolved object chip]
Question input
Mic
Research toggle
Privacy indicator
```

Example:

```text
🎯 Revenue chart   High confidence
"What caused the dip in Q3?"
```

---

# 43. Resolution Chip

Clicking the chip:
- highlights target;
- shows alternatives;
- allows correction.

This is a strong trust mechanic.

---

# 44. Quick Actions

Context-sensitive quick actions:

For text:
- Explain
- Simplify
- Define
- Translate
- Research

For chart:
- Explain trend
- Compare values
- Find anomaly
- Research metric

For equation:
- Explain symbols
- Derive step
- Give intuition

For code:
- Explain
- Find bug
- Why this line?
- Trace variable

These are Skills-like standalone behaviors, not agents.

---

# 45. Answer Scope

Default:
> answer the marked object, not the whole page.

Allow explicit:
> “Use the whole page as context.”

This preserves user intent.

---

# 46. Research UX

A research answer should clearly show:
- page-local understanding;
- outside sources;
- citations;
- date/freshness.

Do not silently mix web research into a local explanation.

---

# 47. Keyboard Accessibility

Support:
- start mark via keyboard;
- cancel;
- ask;
- cycle alternatives;
- open answer panel;
- dismiss.

---

# 48. Screen Reader Compatibility

Because Spatial is visual, accessibility is easy to neglect.

Add:
- ARIA labels to overlay controls;
- live region for resolution;
- textual alternative list;
- keyboard candidate selection.

---

# 49. Internationalization

Keep UI strings centralized.

Semantic resolution can be multilingual later:
- user question language;
- page language;
- answer language.

Do not tie candidate identity to English-only labels.

---

# 50. Standalone Positioning

Spatial should not market itself as:
- browser agent;
- click bot;
- generic AI assistant.

Best positioning:

> **Point at anything on your screen and ask about exactly that.**

More technical:

> **A grounded spatial context layer for the web and PDFs.**

Long-term SDK positioning:

> **Turn human pointing into structured machine context.**

---

# 51. Standalone Customer Segments

Strong standalone segments:

1. students;
2. researchers;
3. developers reading docs/code/web tools;
4. analysts reading charts/reports;
5. support/training users;
6. accessibility use cases;
7. AI tool builders via SDK later.

---

# 52. Packaging

Potential:

### Spatial Free
- local deterministic resolution;
- limited local Q/A;
- browser + PDF;
- basic history.

### Spatial Pro
- research;
- premium models;
- long history;
- voice;
- advanced multi-mark;
- export/share context.

### Spatial Developer
- SDK;
- resolver API;
- custom candidate sources;
- local deployment.

Do not lock pricing before usage data.

---

# 53. SDK Direction

After standalone product quality is high, expose:

```typescript
const context = await spatial.resolve({
  mark,
  question,
  candidates
})
```

This becomes the clean future Orbyn integration.

Potential SDK layers:

```text
@spatial/core
@spatial/browser
@spatial/pdf
@spatial/server
```

Do not prematurely publish until contracts stabilize.

---

# 54. Orbyn Compatibility Boundary

Spatial should export only:

```text
SpatialContext
ResolvedTarget
CandidateObject[]
Confidence
Evidence
```

It should not know:
- Orbyn permissions;
- Missions;
- Needs You;
- Act;
- authority levels.

Later Orbyn consumes Spatial as:

```text
SpatialContext → planning context
```

Orbyn alone maps that context into:
- capability proposal;
- permission;
- approval;
- action;
- verification.

---

# 55. Phase Plan

The implementation should proceed in large gated phases.

---

# PHASE 0 — Freeze Baseline & Build the Test Harness

## Goal
Make the current system measurable before changing resolution behavior.

## Tasks

### 0.1 Document current architecture
Record:
- extension modules;
- server modules;
- request paths;
- provider order;
- config/env;
- privacy modes.

### 0.2 Add version endpoint

```text
GET /v1/health
```

Return:
- app version;
- resolver version;
- OCR version;
- configured providers;
- local-only status.

### 0.3 Create replay format
Store representative current contexts.

### 0.4 Build golden cases
At least:
- 20 web;
- 20 PDF;
- 10 diagram;
- 10 ambiguity;
- 10 failure cases.

### 0.5 Record baseline metrics
- geometric top-1;
- correction rate;
- answer grounding;
- latency.

### 0.6 Add test commands
Example:
```text
pytest tests/resolver
npm test geometry
python scripts/eval_spatial.py
```

## Exit Gate
No architecture changes until baseline can be replayed and measured.

---

# PHASE 1 — Canonical Contracts & Geometry Hardening

## Goal
Ensure every downstream layer operates on stable object contracts.

## Tasks

### 1.1 Implement schema models
- SpatialMark
- CandidateObject
- SpatialContext
- SemanticResolution

Use JSON Schema/Pydantic server-side and validation client-side.

### 1.2 Observation identity
Add:
- observationId;
- contextId;
- requestId;
- markId.

### 1.3 Unify coordinates
Implement explicit conversion helpers.

### 1.4 Geometry features
Add:
- polygon overlap;
- containment;
- center;
- distance;
- mark specificity.

### 1.5 Parent/child structure
Candidates know hierarchy.

### 1.6 Parity tests
Client/server geometry golden tests.

## Exit Gate
Every existing resolver case runs through the new contracts with no regression.

---

# PHASE 2 — Candidate Discovery V2

## Goal
Make sure the correct real object is present before asking intelligence to choose it.

## Tasks

### 2.1 DOM semantics
Capture richer labels/context.

### 2.2 Shadow DOM
Open roots.

### 2.3 Iframes
Same-origin traversal and coordinate transforms.

### 2.4 SVG grouping
Build semantic figure/chart candidates.

### 2.5 PDF grouping
Paragraphs, equations, figures, tables.

### 2.6 OCR candidate blocks
OCR as object candidates.

### 2.7 Canvas fallback
Surrounding semantics + OCR.

### 2.8 Candidate deduplication
Merge equivalent candidates from:
- DOM;
- accessibility;
- OCR.

## Exit Gate
Ground-truth target is present in top candidate pool for >95% of curated supported cases before semantic ranking.

---

# PHASE 3 — System-One Layer & Jev

## Goal
Make semantic resolution explicit, typed, measurable, and independent from answer synthesis.

## Tasks

### 3.1 `SystemOneProvider`
Generic provider abstraction.

### 3.2 `TypeSafeJevProvider`
Implement:
- Choice;
- Noul;
- Score.

### 3.3 Provider gateway
Privacy + timeout + cancellation.

### 3.4 `SemanticTargetResolver`
Inputs:
- question;
- mark;
- candidate set;
- page context.

### 3.5 Reference phrase extraction
Start simple:
- this chart;
- that table;
- this equation;
- here;
- highlighted section.

Do not over-rely on phrase extraction; full question still matters.

### 3.6 Candidate serialization
Send minimal semantic representation.

### 3.7 Jev eval
Compare against baseline.

### 3.8 Abstention
Support no-confident-pick.

### 3.9 Fallback
Jev unavailable → local resolver.

## Exit Gate
Jev improves semantic target accuracy or ambiguity handling measurably without increasing false-high-confidence errors beyond accepted threshold.

---

# PHASE 4 — Confidence Calibration & Clarification UX

## Goal
Turn uncertainty into a reliable product behavior.

## Tasks

### 4.1 Confidence dataset
Use golden cases + corrections.

### 4.2 Calibrate geometric confidence

### 4.3 Calibrate semantic confidence

### 4.4 Fuse confidence
Initial transparent policy.

### 4.5 UX states
- confident;
- ambiguous;
- unresolved.

### 4.6 Alternative candidate UI
Show numbered objects.

### 4.7 Correction capture
Store user final selection.

## Exit Gate
Ambiguous cases produce clarification instead of confidently wrong answers at target rate.

---

# PHASE 5 — Spatial Context V2 / Multi-Mark

## Goal
Make pointing a richer language.

## Tasks

### 5.1 Mark roles
- reference;
- source;
- target;
- compare A/B.

### 5.2 Two-mark resolution

### 5.3 Compare mode

### 5.4 Sequence mode

### 5.5 Bidirectional AI highlights

### 5.6 Resolution chip

## Exit Gate
Multi-mark workflows work across web and PDF without breaking single-mark simplicity.

---

# PHASE 6 — Answer Engine Separation

## Goal
Ensure answer quality benefits from explicit grounding.

## Tasks

### 6.1 Separate resolve endpoint
`/v1/context/resolve`

### 6.2 Answer endpoint consumes SpatialContext
No hidden re-resolution.

### 6.3 Structured prompt builder

### 6.4 Modes
- Explain
- Tutor
- Compare
- Summarize
- Define

### 6.5 Follow-up object inheritance

### 6.6 Context staleness
Re-resolve if needed.

## Exit Gate
Answer model can be swapped without changing target-resolution results.

---

# PHASE 7 — Research, OCR, Vision & Hard Surfaces

## Goal
Handle cases where structured objects are incomplete.

## Tasks

### 7.1 OCR block model

### 7.2 Vision candidate generator

### 7.3 VLM → CandidateObject bridge

### 7.4 Research query generation from resolved object

### 7.5 Source ranking

### 7.6 Citation UI

### 7.7 Scanned PDFs

### 7.8 Complex diagrams

## Exit Gate
Hard-surface fallback remains grounded and visibly lower-confidence rather than pretending DOM-level certainty.

---

# PHASE 8 — Privacy, Security & Local-First Hardening

## Goal
Make standalone Spatial trustworthy enough for sensitive reading/work.

## Tasks

### 8.1 Provider gateway mandatory

### 8.2 Privacy-policy enforcement tests

### 8.3 Sensitive field classifier

### 8.4 Screenshot/crop retention policy

### 8.5 Local-only zero-network integration test

### 8.6 Key management

### 8.7 Extension permission audit

### 8.8 Export/delete history

## Exit Gate
All privacy modes pass automated network/content leakage tests.

---

# PHASE 9 — Performance & Reliability

## Goal
Make the product feel instant and stable.

## Tasks

### 9.1 Profile candidate collection

### 9.2 Cache static semantic metadata

### 9.3 Debounced mutation handling

### 9.4 Async cancellation

### 9.5 SSE event protocol

### 9.6 Provider timeout/fallback

### 9.7 OCR worker lifecycle

### 9.8 Jev latency measurement

### 9.9 Browser zoom/DPI tests

## Exit Gate
Published p50/p95 budgets are met on supported reference hardware/pages.

---

# PHASE 10 — Evaluation & Observability Platform

## Goal
Turn quality improvement into a repeatable engineering process.

## Tasks

### 10.1 Resolution dashboard
Metrics:
- target accuracy;
- abstention;
- corrections;
- latency;
- provider errors.

### 10.2 Answer dashboard

### 10.3 Provider comparison

### 10.4 Replay CLI

### 10.5 Regression CI

### 10.6 Dataset versioning

### 10.7 Privacy-safe traces

## Exit Gate
Every resolver/provider change is evaluated before release.

---

# PHASE 11 — Standalone Productization

## Goal
Make Spatial usable without Orbyn.

## Tasks

### 11.1 Onboarding
30-second tutorial.

### 11.2 Provider setup
Local-first defaults.

### 11.3 Settings
- privacy;
- answer model;
- voice;
- history;
- hotkey.

### 11.4 History UI

### 11.5 Search history

### 11.6 Export context

### 11.7 Packaging
Extension + local server installer.

### 11.8 Auto-update strategy

### 11.9 Crash reporting opt-in

## Exit Gate
A new user can install and answer a marked question without developer assistance.

---

# PHASE 12 — Spatial Developer SDK

## Goal
Make the primitive reusable.

## Tasks

### 12.1 Freeze public SpatialContext schema

### 12.2 JavaScript SDK

### 12.3 Server resolver SDK

### 12.4 Custom candidate-source interface

### 12.5 Local-only embedding

### 12.6 Example integrations

## Exit Gate
A third-party demo can provide candidates and receive a resolved SpatialContext without importing internal extension code.

---

# PHASE 13 — Orbyn Merge Preparation

## Goal
Make Spatial ready to become Orbyn's Spatial Context layer without coupling the standalone product to Orbyn.

## Tasks

### 13.1 Adapter only
Build an optional:

```text
SpatialContext → Orbyn ContextReference
```

adapter.

### 13.2 No Orbyn authority inside Spatial

### 13.3 Candidate ids remain reference-only

### 13.4 Orbyn performs fresh app binding

### 13.5 Orbyn owns:
- permissions;
- Needs You;
- action;
- verification.

### 13.6 End-to-end future test
Example:
```text
circle chart
→ Spatial resolves chart object
→ Orbyn planner proposes change
→ user approves
→ PowerPoint plugin acts
→ verifier checks
```

## Exit Gate
Spatial can be imported or called as a context service without changing its standalone guarantees.

---

# 56. Recommended Repository Layout

```text
extension/
  src/
    content/
      overlay.ts
      marks.ts
      candidates.ts
      highlight.ts
      ask_panel.ts
    background/
      capture.ts
      api.ts
      privacy.ts
      audio.ts
    geometry/
      coordinates.ts
      overlap.ts
      rank.ts
      polygon.ts
    extractors/
      dom.ts
      shadow_dom.ts
      iframe.ts
      svg.ts
      pdf.ts

server/
  app/
    api/
      context.py
      answer.py
      research.py
      audio.py

    resolver/
      deterministic.py
      semantic.py
      confidence.py
      fusion.py

    system_one/
      provider.py
      types.py
      calibration.py
      providers/
        jev.py
        local.py
        deterministic.py

    candidates/
      models.py
      normalize.py
      dedupe.py

    providers/
      answer/
      vision/
      research/
      speech/

    privacy/
      policy.py
      redaction.py
      gateway.py

    store/
      db.py
      contexts.py
      history.py
      corrections.py

    eval/
      replay.py
      metrics.py
      datasets.py

tests/
  geometry/
  extractors/
  resolver/
  jev/
  privacy/
  replay/
  integration/
```

Do not refactor into this entire tree at once. Migrate incrementally by phase.

---

# 57. What Not to Do

Do not:

- replace deterministic geometry with Jev;
- make Jev answer the user's question;
- use raw screenshot → arbitrary click as the main path;
- turn Spatial into an autonomous agent;
- silently send full screens to cloud;
- persist screenshots by default;
- add Orbyn permissions into standalone Spatial;
- treat confidence as correctness;
- hide ambiguity;
- expose internal chain-of-thought;
- couple the product permanently to a single model vendor;
- create different object schemas for DOM/PDF/OCR/VLM;
- let answer providers re-decide the target after semantic resolution.

---

# 58. Final Architecture Principle

The standalone product should follow:

> **Human points → Spatial discovers what exists → geometry narrows where → Jev resolves which object → System Two explains/reasons → Spatial shows exactly what it understood.**

Later, Orbyn adds:

> **permission → authority → execution → independent verification.**

That separation is the strongest possible design.

---

# 59. Immediate Implementation Order

If work starts tomorrow, do this order:

1. freeze/replay current behavior;
2. define canonical schemas;
3. fix coordinate systems;
4. improve candidate extraction;
5. create candidate registry/observation id;
6. build `SystemOneProvider`;
7. integrate Jev;
8. build semantic resolver;
9. add confidence calibration;
10. add clarification UI;
11. separate resolver from answerer;
12. improve PDF/SVG/OCR candidates;
13. add multi-mark;
14. harden privacy;
15. build eval/replay CI;
16. productize standalone;
17. expose SDK;
18. only then build the Orbyn adapter.

---

# 60. Final Product Definition

**Spatial is a local-first spatial grounding system for the web and documents.**

It lets a human refer to information the way humans naturally do:

> “this chart”  
> “this paragraph”  
> “this equation”  
> “these two things”

and turns that reference into a structured, inspectable, confidence-scored machine context.

Its core technical advantage should become:

```text
deterministic geometry
+
real object candidates
+
Jev semantic resolution
+
explicit uncertainty
+
local-first privacy
+
visible grounding
```

The goal is not merely to answer questions from screenshots.

The goal is:

> **Make pointing a reliable machine-readable input modality.**

That makes Spatial valuable on its own and makes it an ideal future primitive inside Orbyn.
