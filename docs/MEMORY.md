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

- **2026-09-24** — NVIDIA probe: `nemotron-3.5-lightning` times out (3/3); `nemotron-3-super-120b-a12b` answers in
  1.5–4 s (now the default); `nemotron-3-ultra-550b` works but ~3–11 s; kimi-k3 / deepseek-v4.1-flash / gpt-oss-20b
  time out; free tier 503s ~1 in 4 → one retry. `glm-5.3` good but 18 s.
- **2026-09-24** — Tavily: CLI + skills installed, browser OAuth done, but keyless monthly cap reached → server
  needs `TAVILY_API_KEY`. Live research ask (DDG fallback): 6.0 s total, Jev routing 371 ms, citation check flagged
  an off-topic source correctly.

- **2026-09-24** — NVIDIA survey (50 chat models, then top 5 × 3 runs, real provider code, thinking off):
  `nemotron-3-super` 8/9 correct, 2.75 s median (1 empty answer) → main; `glm-5.3` 9/9, 4.6 s and `muse-glimmer-30b`
  9/9, 5.4 s → fallbacks; `nemotron-3-ultra` 5/9 (empty answers); `ising-calibration` drops citations. With thinking
  off, `glm-5.3` is 4 s (18 s with reasoning on). Empty answers now count as "busy" and are retried.
- **2026-09-24** — Tavily live: search 1.7 s (5 hits, ranked chunks); full gather incl. Jev ranking 2.7 s; top source
  after ranking answered the question directly.

- **2026-09-24** — UIA spike (`scripts/spikes/uia_region_probe.py`, v3 asks to a live server):
  Calculator (UWP) 16 named elements in 43–64 ms → Jev picked "Memory subtract", correct answer, 2.4–3.4 s end to end;
  Explorer 48 elements in 190 ms → ambiguous box correctly produced 4 clarify chips; Notepad (Win 11, RichEditD2DPT)
  exposes text only via **TextPattern** (Name = "Text editor") → sample points, `RangeFromPoint` + expand to Line gives
  per-line text + exact rects → correct target and answer in 2.9 s. Needs per-monitor DPI awareness
  (`SetProcessDpiAwareness(2)`); `SetForegroundWindow` is refused for background processes (UIA works without it).

- **2026-09-24** — Desktop 4a live on Windows 11: walking a big window's UIA tree (`FindAll` Descendants) took 5.6 s
  on Explorer; probing a 7×7 grid of `ElementFromPoint` in the marked box (+3 ancestors, filtered by the window's pid)
  takes 0.2–0.3 s and follows real z-order — but the overlay must be hidden first or it is what gets hit.
  Hidden-but-"visible" windows exist: filter `DwmGetWindowAttribute(DWMWA_CLOAKED=14)`. RapidOCR first load ≈ 4 s →
  warmed at startup; OCR in `candidates` only when UIA found nothing.

- **2026-09-24** — Privacy review of desktop 4a (before merge): with `SPATIAL_API_TOKEN` unset any web page could POST
  `/api/desktop/capture` (simple request, no preflight) and a DNS-rebinding page could read the frame. Fixed with a
  per-launch desktop token file + custom header and a Host allow-list. Also: the ask-path crop ignored sensitive
  windows, OCR could read a password manager under a small window, unknown process names failed open — all now fail
  closed (see the desktop spec, Security).

- **2026-09-24** — Desktop 4b built with plain `cargo build` (no tauri-cli/npm needed: static `ui/` as `frontendDist`,
  `withGlobalTauri`). Cold compile 2.5 min, incremental ~6 s. UI assets are embedded at compile time → rebuild after
  editing `ui/`. The panel preview must filter huge containers (`anchorFilter`) or the Notepad window itself ranks
  first. Git Bash heredocs containing JS/regex break unpredictably here: write files with the Write tool.

- **2026-09-24** — Speech: NVIDIA hosted Riva works with the normal `nvapi-` key over gRPC `grpc.nvcf.nvidia.com:443`
  with `function-id` metadata (parakeet-tdt-0.6b-v2 `d3fe9151-…`, whisper-large-v3 `b702f636-…`,
  magpie-tts-multilingual `877104f7-…`); build.nvidia.com model pages are JS-rendered, so ids came from a live probe.
  The first RPC is slow (6 s TTS / 22 s ASR: channel + function wake + heavy faster-whisper import) → warm-up makes
  real tiny calls. WebView2 asks for the microphone on every launch and does not remember "Allow", and its prompt is
  invisible to UIA → handled in Rust (`PermissionRequested`, mic + own origin only). An emoji-only `<button>` gets
  the emoji as its UIA name, not its `title`.

- **2026-09-24** — Shared machine Python: `nvidia-riva-client` >= 2.25 pins `protobuf==6.33.5`, which breaks
  tensorflow / grpcio-status / google-ai (need protobuf < 6) → pinned **riva 2.24.0 + protobuf 5.29** (hosted speech
  verified). Machine cleanup the same day: TensorFlow 2.18 (intel/cpu builds) → 2.20 (accepts numpy 2.2), keras
  installed, python-telegram-bot → 22 (httpx 0.28), torch/torchaudio/torchvision → 2.8.0+cu128 + torchcodec 0.7
  (whisperx/pyannote). Only `tribev2`'s metadata cap (torch < 2.7) remains; it imports and runs on 2.8.
  Drive C: was full (835 MB free): pip/npm caches, old %TEMP% and 5.2 GB of `site-packages/~*` rollback folders
  from interrupted installs were deleted. A full C: shows up in Rust as "paging file is too small (os error 1455)"
  and bogus "only metadata stub found for `core`" errors; build with `-j 4`. Release build: 12m44s cold, 8.5 MB exe.

## Gotchas

- **2026-09-28** — The desktop Chrome bridge checks focused Chrome window bounds, then binds the active tab and document when the screen freezes. While paired,
  a blocked, unmatched, or unreadable tab is protected across UIA, OCR, and model crops; a verified safe tab may use
  UIA/OCR if DOM candidates are unavailable. Without pairing, desktop retains its existing UIA/OCR policy.

- **2026-09-26** — The desktop release build uses a PyInstaller server binary as a Tauri bundle resource. Its
  database and optional provider settings live in `%LOCALAPPDATA%\Spatial` (`spatial.db`, `server.env`), never in the
  extracted executable. The Tauri app owns only the server process it spawns and stops that child on exit.
- **2026-09-26** — Bundled server authentication is required: a random per-install bearer token lives in
  `%LOCALAPPDATA%\Spatial\api.token`. Tauri reads it automatically; the extension pairs by copying it from desktop
  Settings into its popup. This closes the default loopback CORS exposure to other installed extensions.
- **2026-09-26** — Provider system prompts must be passed as request-local values through the stream call. A module
  global can cross-contaminate concurrent asks, including the user's explanation level and research instructions.
- **2026-09-26** — System One is opt-in per ask. The first-run Chrome consent and both clients' settings disclose
  TypeSafe's question/candidate-text flow; `system_one: false` skips Jev target judgment, research passage ranking,
  and citation checks together. Disabling only target judgment still sends source text to TypeSafe.

- Citation-check sentence split is naive (`. ` boundaries): initials like "Diederik P. Kingma" split a sentence;
  checks still run per fragment. Improve if it causes false flags.

- `providers._SYSTEM_OVERRIDE` is module-global state (prompt, level, mode): concurrent asks can cross-talk.
  Tolerable for a single-user local server; fix before any multi-user use (backlog).
- httpx `timeout=` is per phase, not a total: System One uses a thread-pool future for a hard budget.

- 2026-09-23 live check: the configured NVIDIA model `nvidia/nemotron-3.5-lightning-30b-a3b` times out (30 s) on
  `main` and on the branch alike, and Ollama is not running → every ask falls back to quoting the marked text.
  Fix the provider (`NVIDIA_MODEL`, start Ollama, or add an OpenRouter/Anthropic key) — not a code issue.

- JS `slice()` can cut an emoji in half; Python/pydantic reject lone surrogates. v2 text goes through `contracts._text` to repair them.
- CORS allows extension origins plus the Tauri origins (`tauri://localhost`, `http(s)://tauri.localhost`) — nothing else.

- A PostToolUse formatter hook reformats Python files after every Write/Edit: re-read before exact-string edits, and don't rely on trailing blank lines in generated blocks.
- Resolver confidence is hand-tuned, not measured — don't trust it for decisions until calibrated.
- JS `geometry.js::rankAnchors` and Python `resolver.py` must stay identical (golden parity test).
- UIA can't read elevated windows from a non-elevated process; Electron apps expose UIA only after
  accessibility is enabled; canvas/game/video apps expose nothing → OCR/vision.

## Open questions

- Jev latency from India for our payload size (docs say 236–276 ms p50 third-party) — measure in E1.
- Does Jev pick the right candidate with qualitative relations only, or does it need coarse numbers?
- Laya zero-shot on our golden set with ≤12 candidates — good enough as a free fallback?
