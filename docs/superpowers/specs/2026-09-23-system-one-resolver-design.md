# System-One Resolver (Jev) — Design

**Date:** 2026-09-23
**Status:** Implemented (2026-09-23, branch `feat/system-one-resolver`)
**Sub-project:** 2 of 5 (roadmap in `docs/TASKS.md`)
**Evidence:** spike results in `docs/TYPESAFE_OPPORTUNITIES.md` → "Results"; script `scripts/experiments/typesafe_experiments.py`

## Goal

On every ask, one Jev (TypeSafe System One) request decides **which object** the user meant and **how to answer**
(kind of help, whether outside facts are needed, whether the thing is visual, whether a follow-up is about the same
thing). Combine it with the deterministic geometry so accuracy rises (eval: 45/49 → 48/49), ambiguity is surfaced
to the user instead of guessed, and research/vision run only when they help.

## Decisions already made

- Jev now; **Laya later** (same `/v1/systemone` protocol — only config changes then). No Laya code in this sub-project.
- **Call Jev on every ask** (≈ 0.5 s on a kept-alive connection), because routing lets most asks skip ~5 s of research.
- Jev **judges only**; it never writes the answer. Geometry stays in code and reaches Jev as words.
- Any Jev failure falls back to today's geometry-only behaviour; an ask never fails because of Jev.

## Non-goals

- Laya backend, fine-tuning, correction-driven training (later).
- E3 passage re-ranking and citation checks (separate follow-up once research traffic exists).
- Desktop / UIA work (sub-projects 3–4).
- Changing the deterministic ranking math (golden parity must stay green).

---

## 1. Components

| File | Responsibility |
|---|---|
| `server/app/system_one.py` (new) | Transport: one kept-alive `httpx.Client` to `{base_url}/v1/systemone`, auth header, timeout, one retry on 429/5xx inside the budget, `warm()` at startup, `status()` for health. Knows nothing about Spatial. |
| `server/app/semantic.py` (new) | Spatial logic: build the Jev state + questions from a `SpatialContext` and the deterministic resolution; parse answers; hybrid target decision; ambiguity rule; routing flags. Pure functions + one `judge()` entry point. |
| `server/app/config.py` | Settings: `SPATIAL_SYSTEM_ONE=jev|off` (default `jev` when `TYPESAFE_API_KEY` is set, else `off`), `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` (default `jev-latest`), `TYPESAFE_BASE_URL` (default `https://api.typesafe.ai`), `SPATIAL_SYSTEM_ONE_TIMEOUT` (default `1.5` s). |
| `server/app/main.py` | Calls `semantic.judge()` in `prepare_ask` after `resolve_marks`, applies the result, gates research, passes routing to the answer layer; FastAPI startup warms the client; `/api/health` gains `system_one`. |
| `server/app/providers.py` | `answer_stream(..., mode=None, prefer_vision=None)`: mode adds one instruction line; `prefer_vision=False` skips the vision attempt. `build_prompt` marks the chosen target and lists the rest as "nearby". |
| `server/app/evaluation.py`, `scripts/eval.py` | `--resolver geometry|hybrid`; hybrid replays recorded Jev answers from a cassette (`--record` refreshes it with the live API). |
| `extension/content.js`, `popup.html` | "Did you mean…?" chips when the server flags ambiguity; chosen chip re-asks with `target_id`; research toggle text becomes "Verify with sources when needed". |

## 2. The Jev request (one per ask)

Built by `semantic.build_request(ctx, resolution, previous_turn)`.

**Shortlist:** the deterministic `anchors_ranked` of the first mark (max 8), lettered A…H. No shortlist
(nothing under the mark) → skip the target question, still ask routing.

**State** (all geometry converted to words in code — the spike showed numbers drop accuracy 43 → 36/49):

```json
{
  "user_question": "why is this step dividing by 2?",
  "mark": "a freehand loop drawn around something",
  "screen": "a PDF document",
  "elements": {
    "A": {"kind": "pdf-text", "text": "dy/dx = (2x)/2 = x", "position": "entirely inside the marked area",
          "size": "about the size of the marked area"},
    "B": {"kind": "pdf-text", "text": "Example 3.2", "position": "partly inside the marked area",
          "size": "much larger than the marked area", "contains_elements": ["A"]}
  },
  "previous_question_in_this_conversation": "what does this line compute?"
}
```

Relation wording is exactly the spike's `qual2` rules: point marks → "the clicked spot is (not) on this element";
open strokes → underline wording ("the stroke is drawn directly under this element, like an underline" / below /
beside / above-not-directly); areas → entirely/mostly/partly inside, "covers the whole marked area", and size
much larger/smaller/about the same; plus `inside_elements` / `contains_elements` from containment. Element text is
capped at 300 chars; `kind` is the candidate's `object_type`.

**Questions** (sent together, evaluated in parallel):

| id | Type | Instructions (abridged) | Used for |
|---|---|---|---|
| `target` | Choice | "Which one element in `elements` is the user referring to?" criteria per letter `element A: <kind> “<text[:80]>”` + `none` | hybrid target, ambiguity |
| `mode` | Choice | "What kind of help does the user want for the marked thing?" 7 modes: explain, define, summarize, compare, translate, debug_error, other | prompt instruction |
| `needs_outside_facts` | Noul | "Does answering require facts not in the marked content that may be current or specific (dates, people, prices, versions, whether a claim is still true)?" | research gate |
| `visual` | Noul | "Is the marked thing mainly visual (chart, diagram, image, icon, UI layout) so the answer must see it?" | vision gate |
| `same_target` | Noul (only on follow-ups) | "Is `user_question` about the same marked thing as the previous question?" | follow-up target reuse |

For routing the state also carries `marked: {kind, text}` = the deterministic top candidate's type and first
300 chars (same content the spike's E2 used).

## 3. Decisions from the answers (`semantic.decide`)

- **Target (hybrid):** if Jev picked a letter (not `none`) with `confidence ≥ 0.5` → that candidate; otherwise the
  deterministic top. Spike: 48/49.
- **Ambiguous:** Jev answered `none`, **or** `p_second / p_first ≥ 0.4` over the letter options. Spike: 0/40 false
  alarms. `clarify` = the top 2–4 candidates by Jev probability (id, text, bbox).
- **Research:** runs when the request allows research **and** (`needs_outside_facts ≥ 0.8` **or** Jev unavailable).
  `research: true` from the extension now means "allowed"; it is no longer "always".
- **Vision:** `prefer_vision = visual ≥ 0.5` when a crop is attached; `None` (today's behaviour) when Jev is unavailable.
- **Follow-ups:** if the previous turn stored a `target_id` and `same_target ≥ 0.5`, keep that target (skip the hybrid
  switch); otherwise decide afresh.
- **Pinned target:** a request with `target_id` (from a "Did you mean" chip) uses that candidate, skips the `target`
  question (routing still asked), and records `label = target_id` in the trace — a correction for eval/training.

Thresholds live as named constants in `semantic.py` (`TARGET_MIN_CONF = 0.5`, `AMBIGUITY_RATIO = 0.4`,
`FACTS_MIN = 0.8`, `VISUAL_MIN = 0.5`, `SAME_TARGET_MIN = 0.5`).

## 4. Applying it in the ask flow

`prepare_ask` order: validate → contract → OCR candidates → deterministic resolve → **`semantic.judge()`** →
reorder `used` so the chosen target is first → research (gated) → answer.

- `resolution_v3` gains: `selected_candidate_id` (hybrid), `alternatives` with Jev probabilities,
  `semantic_confidence` (Jev confidence), `abstained` (= ambiguous), `resolver: "hybrid-jev-1.13"` or
  `"structured-anchor-v1"` on fallback.
- Response gains `routing: {mode, needs_outside_facts, visual, same_target}` (probabilities) and
  `clarify: [{id, text, bbox}]` when ambiguous. `confirmation_required` = ambiguous when Jev answered, else the old rule.
- `build_prompt`: target section first ("The user is asking about: …"), other candidates under "Nearby, probably not
  the target:", plus one line for the mode (e.g. `define` → "Give the meaning in 1–2 sentences.").
- Trace record gains `system_one: {status, model, latency_ms, answers}` and `label` when a chip pinned the target.
- Timings gain `system_one`.

## 5. Extension changes

- When `result.clarify` has ≥ 2 items, the answer shows "Did you mean:" chips (numbered, text ≤ 40 chars) and draws
  matching numbered outlines on the page (reusing the highlight code). Clicking a chip re-asks the same question with
  `target_id` and the same `context_id`.
- The low-confidence note ("circle tighter?") shows only when `confirmation_required` and no `clarify` list.
- Popup: research checkbox label → "Verify with sources when needed (~5 s when used)".
- v2 payload gains optional `target_id` (additive; old servers ignore it).

## 6. Error handling

| Situation | Behaviour |
|---|---|
| No key / `SPATIAL_SYSTEM_ONE=off` | `judge()` returns `None` without a network call; health `system_one.status = "off"` |
| Timeout (> `SPATIAL_SYSTEM_ONE_TIMEOUT`), connect error, 5xx, 429 after one retry | Geometry-only; research allowed = old behaviour; `system_one.status` in response meta + trace = `timeout`/`error`/`rate_limited` |
| 401/403 | As error; health shows `auth_failed` so the user fixes the key |
| Jev answer missing a question / unknown option | That field treated as absent (per-question fallback), others still used |
| Letter maps to no candidate | Treated as `none` |

Startup warm-up failure only logs; the first ask retries the connection.

## 7. Testing

- `test_semantic.py`: relation wording for point / open stroke / area / containment; request shape (letters, `none`,
  follow-up question only with previous turn); `decide()` hybrid threshold, ambiguity ratio, `none`, research and
  vision gates, same-target reuse, pinned `target_id`.
- `test_system_one.py`: transport with `httpx.MockTransport` — auth header, timeout → error status, 429 retry,
  401 → `auth_failed`, off without key (no request made).
- `test_protocol.py` / `test_server.py`: an ask with a fake judge returns `routing`, `clarify`, reordered
  `anchors_used`; research skipped when `needs_outside_facts` low; Jev failure → same response as today.
- Eval: `scripts/eval.py cases --resolver hybrid` replays `server/tests/system_one_cassette.json` (recorded once with
  `--record`); a pytest asserts hybrid top-1 ≥ geometry top-1 and ≥ 47/49 on the cassette.
- Privacy-reviewer subagent on the branch before merge (Jev is a new outbound data flow: question, page title,
  candidate texts — never pixels).

## 8. Budget

≈ 630 input tokens/ask ≈ $0.000026/ask. Latency +≈0.5 s (kept-alive); most asks save ≈5 s by skipping research.

## Implementation notes

- Target gate uses the **pick's probability** (`TARGET_MIN_PROB = 0.5`), not Jev's `confidence`: the recorded eval showed confidence diluted by extra options (47/49 → 49/49). In-sample; revisit with real traces.
- `server/tests/conftest.py` pins the whole test environment (providers off, System One off) so no test can reach real APIs.
