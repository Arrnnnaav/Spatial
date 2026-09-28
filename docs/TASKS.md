# Tasks

*Live board. Update status when you start (`[~]`) or finish (`[x]`) a task; add new tasks as discovered.
Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why).*
**Last updated:** 2026-09-28

## Roadmap

| # | Sub-project | Status | Spec / plan |
|---|---|---|---|
| 1 | Core foundation: independence, contract v3, OCR candidates, trace log, eval harness | Done, merged | `docs/superpowers/specs/2026-09-23-spatial-core-foundation-design.md` |
| 2 | System-One resolver (Jev now, Laya later; geometry fallback) + clarification UI | Done, merged | `docs/superpowers/specs/2026-09-23-system-one-resolver-design.md` |
| 3 | Windows UIA spike (throwaway) | Done 2026-09-24 | `scripts/spikes/uia_region_probe.py` |
| 4 | Desktop app (Tauri, Windows → macOS) | Done 2026-09-24 (4a server, 4b Tauri app; Windows) | `docs/superpowers/specs/2026-09-24-desktop-app-design.md` |
| 5 | Desktop ↔ extension bridge, macOS AX | Bridge in progress; macOS next | `docs/superpowers/specs/2026-09-28-desktop-extension-bridge-design.md` |

## Now

- [x] Review project, docs and plans; brainstorm OS-level direction
- [x] Spec for sub-project 1 (commits `d9f92de`, `1b11bd9`)
- [x] Project docs: AGENTS / PRD / ARCHITECTURE / RULES / DESIGN / TASKS / MEMORY
- [x] Install TypeSafe plugin; brainstorm TypeSafe opportunities (`docs/TYPESAFE_OPPORTUNITIES.md`)
- [x] Write implementation plan for sub-project 1 (`docs/superpowers/plans/2026-09-23-spatial-core-foundation.md`)
- [x] Verify `TYPESAFE_API_KEY` in `server/.env` (live Jev call OK)
- [x] Execute sub-project 1 plan (8 tasks + review fixes; 117 tests pass)
- [x] Final whole-branch review (3 Important fixed)
- [x] Merge `feat/core-foundation` into `main`
- [x] Project automations (hooks, /eval, /sync-docs, privacy-reviewer, context7 + playwright MCP)
- [x] Sub-project 2: Jev experiments E1 + E2

## Sub-project 1 — Core foundation (done)

- [x] A. Remove StudyOS coupling (config, background, content, popup, detect.js, geometry alias, docstrings, README)
- [x] B. `server/app/contracts.py` + v2→v3 conversion + protocol v3 (v2 still accepted)
- [x] B. `scripts/export_schema.py` + `schema/spatial-context.v3.json` + drift test
- [x] C. `ocr_blocks()` + `server/app/candidates.py` (OCR candidates, merge/dedupe); extension sends `crop`
- [x] D. `server/app/trace.py` + `/api/traces*` endpoints + popup toggle + health field
- [x] E. 7 golden + 43 generated eval cases; `scripts/eval.py`; `eval_baseline.json` (top-1 92%)
- [x] Docs: README (tracing, eval), ARCHITECTURE contract section, checklist

## Sub-project 2 — System-One resolver (outline)

- [x] User adds `TYPESAFE_API_KEY` to `server/.env`
- [x] Experiments E1 + E2 (results in `docs/TYPESAFE_OPPORTUNITIES.md`): hybrid 48/49; routing strong
- [x] E3 passage rerank integrated with research
- [ ] E4 Laya evaluation (needs hosted key or local Laya server, then correction data)
- [x] Spec + plan for System-One integration
- [x] `/v1/systemone` client with backend config (Jev / Laya / off)
- [x] Resolver integration + fallback + eval vs baseline (hybrid 50/50 vs geometry 46/50 on recorded cassette)
- [x] Clarification UI ("which one?") + correction capture into trace

## Research v2 (2026-09-24, branch `feat/research-v2`)

- [x] NVIDIA model probe → default `nemotron-3-super-120b-a12b`; one retry on transient errors
- [x] Tavily search layer (+ DDG fallback), credibility dedupe, per-role compare queries; Gemini removed
- [x] Jev passage ranking (E3) + live citation check; ⚠ marker in extension
- [x] Tavily key added; live-verified (search 1.7 s, gather 2.7 s)
- [ ] Offline research eval (10 questions, like the Cited Researcher's judge set)

## Sub-project 3 — Windows UIA spike (outline)

- [x] UIA region → v3 candidates → POST `/api/ask` (spike: `scripts/spikes/uia_region_probe.py`; no hotkey/overlay — that is sub-project 4)
- [x] Tried Notepad, Calculator, File Explorer (VS Code/Chrome skipped: they showed secrets at the time); findings in `MEMORY.md`

## Sub-project 4 — Desktop app

- [x] 4a server: `/api/desktop/capture` (freeze monitor under cursor), `/api/desktop/candidates` (UIA point grid +
      TextPattern of the topmost non-excluded window; password managers never read; OCR fallback), `Ask.capture_id`
      (server-side crop), Tauri CORS origins. Live: capture 0.2 s, candidates 0.2–1.2 s, Notepad ask 5.2 s correct line.
- [x] 4b Tauri app `desktop/`: Alt+Shift+S hotkey, frozen-frame overlay (geometry.js copied at build), hide overlay →
      candidates → `/api/ask/stream` with `capture_id`, panel beside the mark (sources ⚠, clarify chips, settings), tray.
      E2E on Windows 11 (simulated hotkey + drag over a self-opened Notepad): correct line previewed and answered.
- [x] Open source links in the browser (tauri-plugin-opener); markdown lists/headings in the panel
- [~] Release build + installer, autostart, server auto-launch from the tray (NSIS installer built and installed silently; bundled resource matched; bundled server smoke test passed; fresh-profile launch and tray check pending)
- [x] Bundled server requires a persistent random API token; desktop uses it automatically and extension pairs via Settings
- [ ] Multi-monitor + mixed-DPI manual check (overlay sized in physical px per captured monitor)
- [x] Reuse one COM/UIA object per worker thread (cold first call ~1 s)

## Sub-project 5 — Desktop ↔ extension bridge

- [x] Use Chrome DOM candidates for desktop marks over a paired, safe Chrome tab; protect uncertain tabs and retain UIA/OCR fallback for an unpaired or verified safe tab
- [~] Verify the bridge end to end (Chromium DOM, blocked page, wrong bounds and navigation checks passed; desktop overlay/manual disconnect pass pending)
- [ ] macOS AX and screen capture on a Mac

## Speech v2 (2026-09-24, branch `feat/speech-nvidia`)

- [x] NVIDIA hosted Parakeet / Whisper-large-v3 ASR + Magpie TTS as primary, local faster-whisper / pocket-tts
      fallback, 3× busy retry, hard timeout (`server/app/nvidia_speech.py`, `audio.py`)
- [x] Startup warm-up (first real STT 0.48 s / TTS 0.42 s instead of 25–30 s)
- [x] 21 speech tests (`tests/test_audio.py`); privacy review fixes (safe fallback reasons, language check, mic cap)
- [x] Desktop panel 🎤 / 🔊; WebView2 microphone auto-granted for our own pages only; verified E2E
- [ ] Streaming TTS (start playback on the first chunk) and streaming ASR (nemotron-asr-streaming) for long answers
- [ ] Live voice-conversation mode (revisit nemotron-voicechat / PersonaPlex)

## Backlog / ideas

- [x] Pass mode/level/system prompt explicitly to answer providers (remove concurrent ask prompt race)
- [x] Extension: clear stale `pinTarget` on busy/errored asks; pinned re-ask drops the wrong-target turn and
      does not show "circle tighter?"
- [x] Show TypeSafe data flow in extension and desktop settings; per-request System One opt-out also skips
      Jev passage ranking and citation checks
- [x] Flag ambiguity when Jev's pick fails the probability gate; honor 429 Retry-After within the hard budget
- [ ] Multi-mark asks only judge the first mark

- [x] Trace/OCR hardening: stat race, export lock, embedded data URLs, provider error detail, OCR ID collisions,
      candidate cap after OCR, malformed trace replay
- [x] Skip OCR without crop geometry when candidates already have readable text; keep it for text fallback

- [ ] Split `extension/content.js` (560 lines: overlay + panel + anchors) when touching it
- [x] Replace stale production checklist with current Chrome, server and Windows desktop release gates
- [ ] Fine-tune Laya on correction data once ~1–2k labelled resolutions exist
