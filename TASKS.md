# Tasks

*Live board. Update status when you start (`[~]`) or finish (`[x]`) a task; add new tasks as discovered.
Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why).*
**Last updated:** 2026-09-23

## Roadmap

| # | Sub-project | Status | Spec / plan |
|---|---|---|---|
| 1 | Core foundation: independence, contract v3, OCR candidates, trace log, eval harness | Spec approved; plan next | `docs/superpowers/specs/2026-09-23-spatial-core-foundation-design.md` |
| 2 | System-One resolver (`/v1/systemone`: Jev first, Laya second, geometry fallback) + clarification UI | Not started (needs `TYPESAFE_API_KEY`) | `docs/TYPESAFE_OPPORTUNITIES.md` |
| 3 | Windows UIA spike (throwaway) | Not started; can run in parallel | — |
| 4 | Desktop app (Tauri, Windows → macOS) | Blocked on 1, 3 | — |
| 5 | Desktop ↔ extension bridge, macOS AX | Blocked on 4 | — |

## Now

- [x] Review project, docs and plans; brainstorm OS-level direction
- [x] Spec for sub-project 1 (commits `d9f92de`, `1b11bd9`)
- [x] Project docs: AGENTS / PRD / ARCHITECTURE / RULES / DESIGN / TASKS / MEMORY
- [x] Install TypeSafe plugin; brainstorm TypeSafe opportunities (`docs/TYPESAFE_OPPORTUNITIES.md`)
- [ ] Write implementation plan for sub-project 1 (`docs/superpowers/plans/`)

## Sub-project 1 — Core foundation (from spec; refine in plan)

- [ ] A. Remove StudyOS coupling (config, background, content, popup, detect.js, geometry alias, docstrings, README)
- [ ] B. `server/app/contracts.py` + v2→v3 conversion + protocol v3 (v2 still accepted)
- [ ] B. `scripts/export_schema.py` + `schema/spatial-context.v3.json` + drift test
- [ ] C. `ocr_blocks()` + `server/app/candidates.py` (OCR candidates, merge/dedupe); extension sends `crop`
- [ ] D. `server/app/trace.py` + `/api/traces*` endpoints + popup toggle + health field
- [ ] E. Grow golden cases 7 → ~50; `scripts/eval.py`; commit `eval_baseline.json`
- [ ] Docs: README (tracing, eval), ARCHITECTURE contract section, checklist

## Sub-project 2 — System-One resolver (outline)

- [ ] User adds `TYPESAFE_API_KEY` to `server/.env` + shell
- [ ] Experiments E1–E4 (`docs/TYPESAFE_OPPORTUNITIES.md`); propose changes from results
- [ ] `/v1/systemone` client with backend config (Jev / Laya / off)
- [ ] Resolver integration + fallback + eval vs baseline
- [ ] Clarification UI ("which one?") + correction capture into trace

## Sub-project 3 — Windows UIA spike (outline)

- [ ] Hotkey → freeze-frame → box → dump UIA elements under box → POST v3 to `/api/ask`
- [ ] Try on VS Code, Chrome, Word, Figma, File Explorer, a PDF reader; record what UIA returns in `MEMORY.md`

## Backlog / ideas

- [ ] Split `extension/content.js` (560 lines: overlay + panel + anchors) when touching it
- [ ] Clean `SPATIAL_PRODUCTION_CHECKLIST.md` of items no longer relevant
- [ ] Fine-tune Laya on correction data once ~1–2k labelled resolutions exist
