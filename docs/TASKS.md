# Tasks

*Live board. Update status when you start (`[~]`) or finish (`[x]`) a task; add new tasks as discovered.
Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why).*
**Last updated:** 2026-09-23

## Roadmap

| # | Sub-project | Status | Spec / plan |
|---|---|---|---|
| 1 | Core foundation: independence, contract v3, OCR candidates, trace log, eval harness | Done on branch `feat/core-foundation` (review + merge pending) | `docs/superpowers/specs/2026-09-23-spatial-core-foundation-design.md` |
| 2 | System-One resolver (Jev now, Laya later; geometry fallback) + clarification UI | Done on branch `feat/system-one-resolver` (review + merge pending) | `docs/superpowers/specs/2026-09-23-system-one-resolver-design.md` |
| 3 | Windows UIA spike (throwaway) | Not started; can run in parallel | — |
| 4 | Desktop app (Tauri, Windows → macOS) | Blocked on 1, 3 | — |
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

## Sub-project 3 — Windows UIA spike (outline)

- [ ] Hotkey → freeze-frame → box → dump UIA elements under box → POST v3 to `/api/ask`
- [ ] Try on VS Code, Chrome, Word, Figma, File Explorer, a PDF reader; record what UIA returns in `MEMORY.md`

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
