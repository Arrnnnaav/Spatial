# TypeSafe / System One opportunities in Spatial

*Output of the TypeSafe-skill brainstorm (2026-09-23). Experiments are **not run yet**; they need
`TYPESAFE_API_KEY`. Every item is a hypothesis to be tested against the eval harness (sub-project 1)
before it replaces existing code.*

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
