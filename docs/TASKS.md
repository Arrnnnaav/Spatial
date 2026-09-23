# Tasks

*Live board. Update status when you start (`[~]`) or finish (`[x]`) a task; add new tasks as discovered.
Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why).*
**Last updated:** 2026-09-23

## Roadmap

| # | Sub-project | Status | Spec / plan |
|---|---|---|---|
| 1 | Core foundation: independence, contract v3, OCR candidates, trace log, eval harness | Done on branch `feat/core-foundation` (review + merge pending) | `docs/superpowers/specs/2026-09-23-spatial-core-foundation-design.md` |
| 2 | System-One resolver (Jev now, Laya later; geometry fallback) + clarification UI | Done on branch `feat/system-one-resolver` (review + merge pending) | `docs/superpowers/specs/2026-09-23-system-one-resolver-design.md` |
| 3 | Windows UIA spike (throwaway) | Done 2026-09-24 | `scripts/spikes/uia_region_probe.py` |
| 4 | Desktop app (Tauri, Windows → macOS) | Done 2026-09-24 (4a server, 4b Tauri app; Windows) | `docs/superpowers/specs/2026-09-24-desktop-app-design.md` |
| 5 | Desktop ↔ extension bridge, macOS AX | Blocked on 4 | — |

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
- [ ] E3 passage rerank (during integration) · E4 Laya (needs impossibl key)
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
- [ ] Open source links in the browser (tauri-plugin-opener); markdown lists/headings in the panel
- [ ] Release build + installer (`bundle.active`), autostart, server auto-launch from the tray
- [ ] Multi-monitor + mixed-DPI manual check (overlay sized in physical px per captured monitor)
- [ ] Reuse one COM/UIA object per worker thread (cold first call ~1 s)

## Backlog / ideas

- [ ] System One follow-ups (review minors): pass mode/level/system prompt explicitly instead of the shared
      `_SYSTEM_OVERRIDE` (thread race under concurrent asks); popup/consent note + per-request opt-out for the
      TypeSafe data flow (esp. when a local answer model is chosen); flag ambiguity when Jev's pick fails the gate;
      extension: clear stale `pinTarget` on busy/errored asks; pinned re-ask should drop the wrong-target turn and not
      show "circle tighter?"; multi-mark asks only judge the first mark; 429 retry backoff; trace `_scrub` only
      catches a `data:` prefix at string start

- [ ] Trace log hardening (review minors): `status()` stat race on `/api/health`; `export()` reads outside lock;
      OCR candidate ids can collide with client ids; 64-cap only when OCR ran; OCR runs even without crop geometry;
      `run_trace` aborts on one malformed record; provider error text lands in traces

- [ ] Split `extension/content.js` (560 lines: overlay + panel + anchors) when touching it
- [ ] Clean `SPATIAL_PRODUCTION_CHECKLIST.md` of items no longer relevant
- [ ] Fine-tune Laya on correction data once ~1–2k labelled resolutions exist
