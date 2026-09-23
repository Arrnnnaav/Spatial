# TypeSafe / System One opportunities in Spatial

*Output of the TypeSafe-skill brainstorm (2026-09-23). E1 and E2 were run on 2026-09-23 — see **Results** at the end.
Items not yet tested remain hypotheses.*

Jev facts that shape the design (docs.typesafe.ai, jev-1.13): text-only input; 32k tokens for state + longest
question; ~$0.042 / M input tokens, output free; questions in one request run in parallel; weak at
arithmetic, counting, and states full of irrelevant detail → keep geometry in code, send a filtered shortlist.
Laya speaks the same `/v1/systemone` protocol, so every experiment below can be re-run against it by
changing base URL + model id.

## One request per ask ("speculative fan-out")

State (built in code from `SpatialContext`):

```json
{
  "question": "why does this step divide by 2?",
  "surface": {"kind": "pdf", "title": "Calculus notes.pdf", "app": "Chrome"},
  "mark": {"shape": "circle", "role": "reference"},
  "candidates": {
    "A": {"text": "dy/dx = (2x)/2 = x", "kind": "pdf_text", "relation": "fully inside the mark"},
    "B": {"text": "Example 3.2", "kind": "pdf_text", "relation": "partly inside the mark, above"},
    "C": {"text": "Figure 4: slope field", "kind": "ocr", "relation": "touches the mark edge"}
  },
  "previous_turn": {"question": "…", "target": "A"}
}
```

Questions sent together in one call (code uses only what applies):

| # | Question | Primitive | Replaces (fragile code today) | Payoff |
|---|---|---|---|---|
| 1 | Which candidate is the user asking about? (A…L + `none of these`) | Choice | Hand-tuned confidence `0.78 + 0.18·matched` in `resolver.py`; LLM guessing from a dump of 8 anchors in `providers.py::build_prompt` | Real per-candidate probabilities; answer model gets *one* target + alternatives |
| 2 | Does the question clearly refer to one specific candidate? | Noul | `confirmation_required = confidence < 0.6` | Drives the "which one?" UI (DESIGN §2) |
| 3 | What kind of help is asked? explain / define / summarize / compare / translate / debug-error / other | Choice | Nothing (one generic system prompt) | Mode-specific prompts, shorter answers |
| 4 | Does answering need facts beyond the marked content? | Noul | Research toggle always on (adds ~5 s to every ask) | Skip research when not needed → faster, cheaper |
| 5 | Is the marked thing mainly visual (chart, diagram, image, UI layout)? | Noul | `diagram = image and no anchor text` in `providers.py` | Route to vision model only when needed |
| 6 | Is this follow-up about the same target as the previous turn? | Noul | Implicit: `context_id` means same target | Correct follow-up context |
| 7 | How expert is the question's phrasing? (3 levels) | Score | Manual level selector | Default level suggestion |

## Research pipeline (second request, after search)

| # | Question | Primitive | Replaces | Payoff |
|---|---|---|---|---|
| 8 | How well does this passage help answer the question about the marked text? | Score per passage | Term-overlap `research.py::select_passages` | Better sources (TypeSafe rerank cookbook: large top-1 gains over BM25) |
| 9 | Does source [n] support this sentence of the answer? | Choice (supports / contradicts / unrelated) per claim | `cited_ids` regex (only checks the number exists) | Flag unsupported citations |

## OS-level (desktop, sub-project 4)

| # | Question | Primitive | Payoff |
|---|---|---|---|
| 10 | Is this UIA element content or app chrome (toolbar, ribbon, scrollbar)? | Noul per element (batched) | UIA trees are noisy; replaces fragile area/role heuristics like `anchorFilter` |
| 11 | Is this screen sensitive (banking, health, password manager)? — from window title, process, visible labels | Noul | Replaces site-regex `BLOCKLIST` where no URL exists |

## Correction loop → Laya

Every "which one?" answer is a labelled `(state, correct candidate)` pair. Stored in the trace log, these
become the fine-tuning set for Laya (its README: element selection 0.10 zero-shot → 0.66 after fine-tuning).

## Experiments to run (when `TYPESAFE_API_KEY` is set)

Script: `scripts/typesafe_experiments.py` (to be written in sub-project 2).

1. **E1 target selection:** golden cases → Q1 (+Q2). Compare top-1 vs deterministic geometry; vary
   relation wording (qualitative vs numeric) and candidate count (4 / 8 / 12). Record latency + cost.
2. **E2 routing:** ~40 hand-written questions labelled for Q3–Q6; accuracy per question, one request each.
3. **E3 passage rerank:** 10 research asks, compare Q8 ranking vs `select_passages` by manual relevance labels.
4. **E4 Laya:** re-run E1–E2 against Laya (impossibl hosted) with the same client.

Decision rule: adopt a question only if it beats the current code on the eval set without pushing
resolution p95 past 400 ms.

## Results (2026-09-23, jev-1.13.0) — `scripts/experiments/typesafe_experiments.py`, raw rows in `scripts/experiments/results/`

**E1 — which element + ambiguity (49 single-mark eval cases, one request each, ≤8 shortlisted candidates)**

| Variant | Top-1 | Notes |
|---|---|---|
| Deterministic geometry (baseline) | 45/49 | misses: 3× point-on-toolbar-button, 1× underline |
| Jev, geometry as **numbers** | 36/49 | confirms docs: numbers hurt; OCR labels lost to the containing canvas |
| Jev, geometry as **words** (`qual`) | 43/49 | fixes all point-on-button cases (web 15/15); fails underlines (chose "none") |
| Jev, words + **stroke wording** (`qual2`) | 44/49 | underlines fixed; remaining misses = 4 ambiguous (answers "none") + golden `point_mark` |
| **Hybrid**: Jev pick if confidence ≥ 0.5, else geometry | **48/49** | only miss: golden `point_mark` (label is a regression expectation, not a human intent label) |

- Ambiguity: the separate Noul "could it be two or more?" is noisy (at 0.6: 8/8 ambiguous flagged but 12/40 clear
  wrongly flagged). **Better signal from the Choice itself**: flag when Jev answers `none` or
  `second_prob / first_prob ≥ 0.4` → 4/8 ambiguous flagged, **0/40 false alarms**. The unflagged 4 are cases where
  either answer is acceptable (image vs caption, adjacent cells) and Jev picked one confidently.
- Cost ≈ 630 input tokens ≈ **$0.000026 per ask**.

**E2 — routing (40 hand-labelled asks, one request each)**

| Question | Result |
|---|---|
| Help mode (7-way Choice) | 38/40 (both misses arguably label errors: "who invented this?" → `other`) |
| Mainly visual (Noul ≥ 0.5) | **40/40** |
| Same target as previous turn (Noul ≥ 0.5) | **6/6** |
| Needs outside facts (Noul) | ≥ 0.8: recall 7/7, false positive 4/33 · ≥ 0.9: 6/7, 0/33 |

**Latency** (from India): new connection per call ≈ 1.1–2.5 s (plain TLS round-trip alone ≈ 1 s); **kept-alive
connection ≈ 450–500 ms** per call regardless of size. So: one persistent client, warm at startup, one request per ask.

**Not run yet:** E3 passage rerank (needs live research traffic — do during integration); E4 Laya (needs an
impossibl key; our state is ~600 tokens > the 512-token English checkpoint, so hosted 8192 or multilingual 1024 only).
