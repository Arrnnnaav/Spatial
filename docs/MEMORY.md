# Memory

*Project memory: dated decisions, facts learned, gotchas and open questions — things not obvious from the
code or git log. Newest first within each section. Remove entries that become wrong.*

## Decisions

- **2026-09-23** — Order of work: shared foundation (sub-project 1) + System-One resolver before browser-only
  polish; Windows UIA spike in parallel. Reason: accuracy work is mostly server-side and helps browser and
  desktop alike; OS-level unknowns should be de-risked early.
- **2026-09-23** — Desktop: Windows first, stack must port to macOS soon → Tauri (user answer "B").
- **2026-09-23** — Jev first for System One; Laya (same `/v1/systemone` protocol) evaluated alongside and is the
  long-term fine-tuning path. Neither answers the user; they only judge.
- **2026-09-23** — Local/privacy-first is **not** a current priority; cloud APIs are fine. Keep existing
  privacy tiers, don't extend them.
- **2026-09-23** — Remove all StudyOS coupling; this repo is the single source of truth.
- **2026-09-23** — Trace log: option B (metadata + resolution trace, never pixels), opt-in, `%APPDATA%\Spatial\logs`.

## Facts learned

- **Jev (TypeSafe, launched 2026-09-15):** `POST https://api.typesafe.ai/v1/systemone`; model `jev-latest`
  (= `jev-1.13.0`); primitives Choice / Score / Noul; text-only; 64k per request, 32k state + longest
  question; $0.042/M input tokens, output free; 1,200 req/min. Weak at math, counting, literal reading,
  large irrelevant state. Python SDK `typesafe_sdk` (`TypeSafeClient`, `Noul`, …). Docs index:
  https://docs.typesafe.ai/llms.txt.
- **Laya (github.com/NandhaKishorM/laya, Apache-2.0, created 2026-09-18):** Jev-wire-compatible encoder
  models (ModernBERT-large 421M / mmBERT-base 322M); context only 512–1024 tokens locally (8192 on impossibl
  hosted, free); 33 ms GPU, 190–460 ms CPU; weak above ~20 options; **UI element selection 0.10 zero-shot →
  0.66 fine-tuned** (their browser-agent write-up). Benchmarks are self-reported; open issues #185 (act head
  saturates) and #208 (calibration numbers don't reproduce).
- User linked "layacheck" — that repo 404s; assumed `laya`.
- Server reads `server/.env` via python-dotenv (`server/app/config.py`).
- Tests (2026-09-23, after sub-project 1): server pytest 117 passed; extension geometry tests pass.
- TypeSafe plugin installed at user scope (`typesafe@typesafe-ai` v0.5.7); its skill appears after a
  Claude Code restart (skill file: `~/.claude/plugins/cache/typesafe-ai/typesafe/*/skills/typesafe-ai/SKILL.md`).

- **2026-09-23** — First live Jev call with the `server/.env` key: 200 OK, ~1.2 s round trip (India), 401 input
  tokens for 2 candidates. Thin criteria ("candidate A") → Jev chose `none` (confidence 0.17): criteria must
  describe each candidate concretely.

- **2026-09-23** — Resolver eval baseline (50 cases: 7 golden + 43 generated): top-1 92%, top-3 100%, abstain 0%.
  Misses: all 3 point-on-toolbar-button cases (container and button tie at 0.95, longer text wins → container),
  1 PDF underline. Ambiguous cases are never flagged (confidence is hand-tuned) — the main target for Jev.
- **2026-09-23** — OCR (RapidOCR) verified locally: returns per-word/phrase boxes, e.g. "Revenue" + "by quarter".
- **2026-09-23** — With OCR candidates, the "diagram" note is only added when OCR also found no text.
- **2026-09-23** — A request without `protocol_version` is v2; v3 = version >= 3 or a `context` field.

- **2026-09-23** — Jev spike (E1/E2): hybrid (Jev pick if conf ≥ 0.5 else geometry) = 48/49 vs 45/49; geometry must be
  described in **words** (numbers: 36/49); open strokes need their own wording ("drawn directly under this element").
  Ambiguity = Jev answers `none` or p2/p1 ≥ 0.4 (0/40 false alarms); separate ambiguity Noul too noisy.
  Routing: visual 40/40, same-target 6/6, mode 38/40, needs-facts use ≥ 0.8. ≈ $0.000026/ask.
- **2026-09-23** — Jev latency from India: ≈ 1 s TLS setup per new connection; ≈ 470 ms per call on a kept-alive
  connection. Use one persistent client and warm it at server start.

- **2026-09-23** — System One integrated. Recorded eval (cassette, jev-1.13.0): hybrid **50/50** vs geometry 46/50;
  7/50 asks flagged ambiguous (3 of 8 ambiguous-labelled; the rest are close calls where chips are still reasonable).
  Warm keep-alive latency p50 ≈ 385 ms, p95 ≈ 494 ms per Jev call from India.
- **2026-09-23** — Hybrid gate must use the pick's **probability**, not `confidence` (diluted by extra options).
- **2026-09-23** — Running one test file alone used to hit real providers from server/.env; `tests/conftest.py`
  now pins providers/System One off for every test.

## Gotchas

- 2026-09-23 live check: the configured NVIDIA model `nvidia/nemotron-3.5-lightning-30b-a3b` times out (30 s) on
  `main` and on the branch alike, and Ollama is not running → every ask falls back to quoting the marked text.
  Fix the provider (`NVIDIA_MODEL`, start Ollama, or add an OpenRouter/Anthropic key) — not a code issue.

- JS `slice()` can cut an emoji in half; Python/pydantic reject lone surrogates. v2 text goes through `contracts._text` to repair them.
- CORS allows only extension origins; a future desktop (Tauri) client origin must be added explicitly.

- A PostToolUse formatter hook reformats Python files after every Write/Edit: re-read before exact-string edits, and don't rely on trailing blank lines in generated blocks.
- Resolver confidence is hand-tuned, not measured — don't trust it for decisions until calibrated.
- JS `geometry.js::rankAnchors` and Python `resolver.py` must stay identical (golden parity test).
- UIA can't read elevated windows from a non-elevated process; Electron apps expose UIA only after
  accessibility is enabled; canvas/game/video apps expose nothing → OCR/vision.

## Open questions

- Jev latency from India for our payload size (docs say 236–276 ms p50 third-party) — measure in E1.
- Does Jev pick the right candidate with qualitative relations only, or does it need coarse numbers?
- Laya zero-shot on our golden set with ≤12 candidates — good enough as a free fallback?
