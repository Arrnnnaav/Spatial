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
- Baseline tests (2026-09-23): server pytest 33 passed; extension geometry tests pass.
- TypeSafe plugin installed at user scope (`typesafe@typesafe-ai` v0.5.7); its skill appears after a
  Claude Code restart (skill file: `~/.claude/plugins/cache/typesafe-ai/typesafe/*/skills/typesafe-ai/SKILL.md`).

- **2026-09-23** — First live Jev call with the `server/.env` key: 200 OK, ~1.2 s round trip (India), 401 input
  tokens for 2 candidates. Thin criteria ("candidate A") → Jev chose `none` (confidence 0.17): criteria must
  describe each candidate concretely.

## Gotchas

- Resolver confidence is hand-tuned, not measured — don't trust it for decisions until calibrated.
- JS `geometry.js::rankAnchors` and Python `resolver.py` must stay identical (golden parity test).
- `extension/detect.js` is dead (dashboard-only, not in manifest).
- UIA can't read elevated windows from a non-elevated process; Electron apps expose UIA only after
  accessibility is enabled; canvas/game/video apps expose nothing → OCR/vision.

## Open questions

- Jev latency from India for our payload size (docs say 236–276 ms p50 third-party) — measure in E1.
- Does Jev pick the right candidate with qualitative relations only, or does it need coarse numbers?
- Laya zero-shot on our golden set with ≤12 candidates — good enough as a free fallback?
